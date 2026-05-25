"""Load the reviewed sku_recipe_mapping_candidates.csv into DuckDB and
build the derived ingredient_consumption_daily table.

Schema follows the 1:many override documented in CLAUDE.md §1.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO_ROOT / "data" / "sku_recipe_mapping_candidates.csv"
DEFAULT_DB = REPO_ROOT / "data" / "kfc.duckdb"

MAPPED_BANDS = {"exact", "close", "approximate",
                "composite_decomposed", "composite_partial"}


def load(csv_path: Path, db_path: Path) -> dict:
    df = pd.read_csv(csv_path)
    df = df[df["recipe_template_id"].notna() & (df["recipe_template_id"] != "")]
    df = df[df["confidence_band"].isin(MAPPED_BANDS)]
    df["quantity"] = df["quantity"].astype(float)
    df["mapped_by"] = df.apply(
        lambda r: "manual" if r["approved_by_reviewer"] else "system", axis=1
    )
    df["mapped_at"] = datetime.utcnow()
    df = df[[
        "real_sku_id", "recipe_template_id", "recipe_template_name", "quantity",
        "confidence_band", "component_role", "note", "approved_by_reviewer",
        "mapped_by", "mapped_at",
    ]]
    con = duckdb.connect(str(db_path))
    try:
        con.execute("DROP TABLE IF EXISTS sku_recipe_mapping")
        con.register("_m", df)
        con.execute("CREATE TABLE sku_recipe_mapping AS SELECT * FROM _m")
        con.unregister("_m")
        n = con.execute("SELECT COUNT(*) FROM sku_recipe_mapping").fetchone()[0]
        n_skus = con.execute(
            "SELECT COUNT(DISTINCT real_sku_id) FROM sku_recipe_mapping"
        ).fetchone()[0]
        # Coverage of POS revenue
        rev = con.execute(
            """
            SELECT
              SUM(CASE WHEN m.real_sku_id IS NOT NULL THEN li.line_total ELSE 0 END)
                AS mapped_rev,
              SUM(li.line_total) AS total_rev
            FROM pos_line_items li
            LEFT JOIN (
              SELECT DISTINCT real_sku_id FROM sku_recipe_mapping
            ) m ON m.real_sku_id = li.product_id
            """
        ).fetchone()
    finally:
        con.close()
    return {
        "rows": n,
        "real_skus_mapped": n_skus,
        "revenue_coverage": float(rev[0]) / float(rev[1]) if rev[1] else 0.0,
        "mapped_rev_pkr": float(rev[0] or 0),
        "total_rev_pkr": float(rev[1] or 0),
    }


def build_consumption(db_path: Path) -> dict:
    """Compute ingredient_consumption_daily from POS × recipes × mapping.

    Direct-ingredient mapping rows (recipe_template_id LIKE 'ING-%') route
    straight to the named ingredient; SKU rows route through the recipe BOM.
    """
    con = duckdb.connect(str(db_path))
    try:
        con.execute("DROP TABLE IF EXISTS ingredient_consumption_daily")
        con.execute(
            """
            CREATE TABLE ingredient_consumption_daily AS
            WITH expanded AS (
              SELECT
                CAST(li.transaction_timestamp AS DATE) AS date,
                li.store_id,
                li.product_id,
                li.quantity                                  AS pos_quantity,
                m.recipe_template_id                         AS target_id,
                m.quantity                                   AS bundle_qty
              FROM pos_line_items li
              JOIN sku_recipe_mapping m
                ON m.real_sku_id = li.product_id
            ),
            direct_ing AS (
              SELECT e.date, e.store_id, e.target_id AS ingredient_id,
                     e.pos_quantity * e.bundle_qty AS qty,
                     i.unit AS unit
              FROM expanded e
              JOIN ingredients i ON i.ingredient_id = e.target_id
              WHERE e.target_id LIKE 'ING-%'
            ),
            via_recipes AS (
              SELECT e.date, e.store_id, r.ingredient_id,
                     e.pos_quantity * e.bundle_qty * r.quantity_per_unit AS qty,
                     r.unit
              FROM expanded e
              JOIN recipes r ON r.sku_id = e.target_id
              WHERE e.target_id LIKE 'SKU-%'
            )
            SELECT date, store_id, ingredient_id,
                   SUM(qty) AS consumed_qty,
                   ANY_VALUE(unit) AS unit,
                   'derived' AS provenance
            FROM (SELECT * FROM direct_ing UNION ALL SELECT * FROM via_recipes)
            GROUP BY date, store_id, ingredient_id
            """
        )
        n_rows = con.execute(
            "SELECT COUNT(*) FROM ingredient_consumption_daily"
        ).fetchone()[0]
        n_days = con.execute(
            "SELECT COUNT(DISTINCT date) FROM ingredient_consumption_daily"
        ).fetchone()[0]
        n_ing = con.execute(
            "SELECT COUNT(DISTINCT ingredient_id) FROM ingredient_consumption_daily"
        ).fetchone()[0]
        top = con.execute(
            """
            SELECT i.name, SUM(c.consumed_qty) AS total_qty, ANY_VALUE(c.unit) AS unit
            FROM ingredient_consumption_daily c
            JOIN ingredients i ON i.ingredient_id = c.ingredient_id
            GROUP BY i.name
            ORDER BY total_qty DESC
            LIMIT 8
            """
        ).fetchall()
    finally:
        con.close()
    return {"rows": n_rows, "days": n_days, "ingredients": n_ing, "top": top}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args(argv)

    stats = load(args.csv, args.db)
    print(f"sku_recipe_mapping rows: {stats['rows']:,}")
    print(f"distinct real SKUs mapped: {stats['real_skus_mapped']}")
    print(f"POS revenue coverage: {stats['revenue_coverage']*100:.2f}% "
          f"({stats['mapped_rev_pkr']:,.0f} / {stats['total_rev_pkr']:,.0f} PKR)")
    if stats["revenue_coverage"] < 0.75:
        print("WARNING: below 75% coverage gate", file=sys.stderr)
        sys.exit(1)

    cstats = build_consumption(args.db)
    print()
    print(f"ingredient_consumption_daily rows: {cstats['rows']:,}")
    print(f"  days: {cstats['days']}   ingredients: {cstats['ingredients']}")
    print(f"  top by total consumption:")
    for name, qty, unit in cstats["top"]:
        print(f"    {name:<35}  {qty:>14,.2f} {unit}")


if __name__ == "__main__":
    main()
