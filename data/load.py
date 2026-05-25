"""Bootstrap DuckDB from the Railway POS feed and seed CSVs.

First-time setup: `python data/load.py`.
See SPEC.md Section 9 (Phase 1) and CLAUDE.md Section 1.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.load_real_pos import (  # noqa: E402
    DEFAULT_CACHE,
    DEFAULT_DB,
    build_frames,
    fetch_transactions,
    load_into_duckdb,
    status,
)

SEED_DIR = REPO_ROOT / "data" / "seed"

MODELLED_TABLES = {
    "nodes": "01_nodes.csv",
    "suppliers": "03_suppliers.csv",
    "ingredients": "04_ingredients.csv",
    "skus": "05_skus.csv",
    "recipes": "06_recipes.csv",
    "purchase_orders": "09_purchase_orders.csv",
    "deliveries": "10_deliveries.csv",
    "invoices": "11_invoices.csv",
    "payments": "12_payments.csv",
}

# Seed 02_stores.csv is supplemental metadata only — joined onto real POS stores
# where IDs match. The synthetic format mismatches real POS (S-0001 vs 0249),
# so the join is empty for now. Recorded for completeness.
SUPPLEMENTAL_STORE_SEED = "02_stores.csv"

# Per-supplier baseline pass-rate noise — quality-variance injection on
# deliveries (CLAUDE.md Section 1). Some suppliers are consistently better.
SUPPLIER_QUALITY_BASELINE: dict[str, float] = {
    "SUP-001": 0.985,
    "SUP-002": 0.972,
    "SUP-003": 0.965,
    "SUP-004": 0.978,
    "SUP-005": 0.955,
    "SUP-006": 0.973,
    "SUP-007": 0.990,
    "SUP-008": 0.962,
    "SUP-009": 0.980,
    "SUP-010": 0.945,
    "SUP-011": 0.968,
    "SUP-012": 0.955,
    "SUP-013": 0.960,
    "SUP-014": 0.940,
    "SUP-015": 0.974,
}


def inject_quality_variance(deliveries: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Make quality_pass_qty deviate from delivered_qty in a supplier-correlated way."""
    df = deliveries.copy()
    baselines = df["supplier_id"].map(SUPPLIER_QUALITY_BASELINE).fillna(0.96)
    noise = rng.normal(loc=0.0, scale=0.025, size=len(df))
    pass_rate = (baselines + noise).clip(0.92, 1.00).astype(float)
    df["quality_pass_qty"] = (df["delivered_qty"] * pass_rate).round(2)
    df["quality_pass_rate"] = pass_rate
    df["quality_variance_injected"] = True
    return df


def write_table(con: duckdb.DuckDBPyConnection, name: str, df: pd.DataFrame, provenance: str) -> None:
    df = df.copy()
    df["provenance"] = provenance
    con.execute(f"DROP TABLE IF EXISTS {name}")
    con.register("_tmp", df)
    con.execute(f"CREATE TABLE {name} AS SELECT * FROM _tmp")
    con.unregister("_tmp")


_DATE_COLUMNS = {
    "purchase_orders": ["po_date", "expected_delivery_date"],
    "deliveries": ["delivery_date"],
    "invoices": ["invoice_date", "due_date"],
    "payments": ["payment_date"],
    "skus": ["introduced"],
}

# Modelled supply chain in seed CSVs spans 2025-01 to 2025-06; real POS
# spans 2026-03 to 2026-05+. Shift modelled dates forward so the two
# streams align temporally for the credit-product demo. Documented in
# About page caveats.
MODELLED_DATE_SHIFT_MONTHS = 14


def _shift_dates(series: pd.Series, months: int) -> pd.Series:
    return (pd.to_datetime(series, errors="coerce")
              + pd.DateOffset(months=months)).dt.date


def load_modelled(db_path: Path) -> None:
    rng = np.random.default_rng(seed=20260525)
    con = duckdb.connect(str(db_path))
    try:
        for table, fname in MODELLED_TABLES.items():
            df = pd.read_csv(SEED_DIR / fname)
            for col in _DATE_COLUMNS.get(table, []):
                if table == "skus":
                    df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
                else:
                    df[col] = _shift_dates(df[col], MODELLED_DATE_SHIFT_MONTHS)
            if table == "deliveries":
                df = inject_quality_variance(df, rng)
            write_table(con, table, df, provenance="modelled")
            print(f"[mod] {table}: {len(df):,} rows  ({fname})")

        # Supplemental store metadata — kept on disk only; not promoted to a
        # table because store IDs don't reconcile with the real POS feed.
        con.execute("DROP TABLE IF EXISTS store_routing")
        con.execute(
            """
            CREATE TABLE store_routing AS
            SELECT
              store_id,
              CAST('COM-KHI-01' AS VARCHAR) AS served_by_commissary_id,
              CAST('WHC-KHI-01' AS VARCHAR) AS served_by_cold_warehouse_id,
              CAST('WHD-KHI-01' AS VARCHAR) AS served_by_dry_warehouse_id,
              CAST('modelled-default' AS VARCHAR) AS routing_source,
              'modelled' AS provenance
            FROM store_summary
            """
        )
        n = con.execute("SELECT COUNT(*) FROM store_routing").fetchone()[0]
        print(f"[mod] store_routing: {n} rows (default → COM-KHI-01 for all real stores)")
    finally:
        con.close()


def main() -> None:
    print("=== KFC Ontology — bootstrap load ===")
    st = status()
    print(f"[net] receiver status={st.get('status')} server_count={st.get('transactions'):,}")

    records = fetch_transactions(DEFAULT_CACHE)
    tx_df, li_df, stats = build_frames(records)
    print(f"[pos] quality filter: {stats}")
    load_into_duckdb(DEFAULT_DB, tx_df, li_df)
    load_modelled(DEFAULT_DB)

    # Phase 1 step 4/5: load reviewed recipe mapping + derive consumption.
    candidates = REPO_ROOT / "data" / "sku_recipe_mapping_candidates.csv"
    if candidates.exists():
        from scripts.load_recipe_mapping import load as _load_map, build_consumption
        mapstats = _load_map(candidates, DEFAULT_DB)
        print(f"[map] sku_recipe_mapping rows: {mapstats['rows']:,}, "
              f"coverage={mapstats['revenue_coverage']*100:.2f}%")
        cstats = build_consumption(DEFAULT_DB)
        print(f"[der] ingredient_consumption_daily: {cstats['rows']:,} rows "
              f"over {cstats['days']} days, {cstats['ingredients']} ingredients")
    else:
        print("[map] sku_recipe_mapping_candidates.csv not found — "
              "run scripts/compute_all_recipes.py then re-run load.py")

    con = duckdb.connect(str(DEFAULT_DB), read_only=True)
    try:
        print()
        print("=== final table catalogue ===")
        for name, kind in con.execute(
            "SELECT table_name, table_type FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY table_name"
        ).fetchall():
            n = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            print(f"  {name:<22} {n:>10,}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
