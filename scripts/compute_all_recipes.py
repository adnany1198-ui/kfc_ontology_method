"""Generate sku_recipe_mapping_candidates.csv (CLAUDE.md Section 1, Phase 1 step 4).

Reads the 420 real POS menu items and the 31 modelled recipe templates,
runs fuzzy matching, and writes a CSV for Adnan to review.

Halts at Gate 1: no DB write happens here. After Adnan edits the CSV, a
follow-up step loads it into the `sku_recipe_mapping` table.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import duckdb
import pandas as pd
from rapidfuzz import fuzz, process

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "kfc.duckdb"
DEFAULT_OUT = REPO_ROOT / "data" / "sku_recipe_mapping_candidates.csv"

# Stopwords stripped before fuzzy matching to focus on the dish identity.
_NOISE_TOKENS = {
    "ALACARTE", "ALA", "CARTE", "COMBO", "MEAL", "BOX", "BUCKET", "DEAL",
    "WITH", "AND", "FOR", "THE", "SET", "VALUE", "FAMILY", "WOW", "EXTREME",
    "XTREME", "FEAST", "FESTIVAL", "SPECIAL", "PACK", "OFFER", "GOLOOTLO",
    "DRIVE", "THRU", "THORUGH", "DELIVERY", "EAT", "OUT", "DELIVERY",
    "TAKE", "AWAY",
}
_COMPOSITE_HINTS = (
    "FAMILY", "FESTIVAL", "BUCKET", "BOX", "COMBO", "MEAL", "FEAST",
    "DEAL", "DUO", "GOLOOTLO", "CHIPS", "STRIPS, CHIPS", "WOW",
    "VALUE", "RICE", "TWIST", "XTREME", "WITH",
)
_WASTAGE_HINT = ("WASTAGE", "MODIFIER")

# Per-template manual aliases to help fuzzy match in tricky cases.
_TEMPLATE_ALIASES: dict[str, list[str]] = {
    "SKU-001": ["ZINGER BURGER", "ZINGER", "ZINGER ALACARTE"],
    "SKU-002": ["ZINGER STACKER", "STACKER"],
    "SKU-003": ["ZINGER JUNIOR", "JUNIOR"],
    "SKU-004": ["MIGHTY ZINGER", "MIGHTY ZINGER BURGER"],
    "SKU-005": ["KRUNCH BURGER", "KRUNCH"],
    "SKU-010": ["HOT AND CRISPY 2 PCS", "H&C 2", "HOT CRISPY 2PC"],
    "SKU-011": ["HOT AND CRISPY 3 PCS", "H&C 3", "HOT CRISPY 3PC"],
    "SKU-012": ["HOT AND CRISPY 5 PCS", "H&C 5", "HOT CRISPY 5PC"],
    "SKU-013": ["HOT AND CRISPY 8 PCS BUCKET", "H&C 8 BUCKET"],
    "SKU-014": ["HOT AND CRISPY 12 PCS BUCKET", "H&C 12 BUCKET"],
    "SKU-015": ["HOT AND CRISPY 21 PCS BUCKET", "H&C 21 BUCKET"],
    "SKU-020": ["HOT WINGS 6 PCS"],
    "SKU-021": ["HOT WINGS 12 PCS", "HOT WINGS 10 PCS"],
    "SKU-022": ["CHICKEN STRIPS 3 PCS", "STRIPS 3"],
    "SKU-023": ["CHICKEN STRIPS 5 PCS", "STRIPS 5", "STRIPS 4"],
    "SKU-030": ["TWISTER WRAP", "TWISTER"],
    "SKU-031": ["CHICKEN SNACKER TWISTER", "SNACKER"],
    "SKU-040": ["RICE AND SPICE", "RICE N SPICE", "RICE & SPICE"],
    "SKU-041": ["BONELESS CHICKEN BUCKET", "BONELESS BUCKET"],
    "SKU-050": ["FRIES REGULAR", "FRENCH FRIES REGULAR"],
    "SKU-051": ["FRIES LARGE", "FRENCH FRIES LARGE"],
    "SKU-052": ["COLESLAW", "COLE SLAW"],
    "SKU-053": ["CORN ON THE COB", "CORN COB"],
    "SKU-060": ["PEPSI REGULAR"],
    "SKU-061": ["PEPSI LARGE"],
    "SKU-062": ["7UP REGULAR", "SEVEN UP"],
    "SKU-063": ["MOUNTAIN DEW REGULAR", "MOUNTAIN DEW", "DEW"],
    "SKU-064": ["MINERAL WATER", "WATER"],
    "SKU-070": ["SOFT SERVE CONE", "ICE CREAM CONE"],
    "SKU-071": ["KRUSHER CHOCOLATE"],
    "SKU-072": ["KRUSHER STRAWBERRY"],
}

_BAND_THRESHOLDS = [("exact", 95.0), ("close", 80.0), ("approximate", 60.0)]


def normalise(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = name.upper()
    s = re.sub(r"[\(\)\[\]\{\}]", " ", s)
    s = re.sub(r"[^A-Z0-9& +]", " ", s)
    s = s.replace("&", " AND ")
    s = re.sub(r"\s+", " ", s).strip()
    tokens = [t for t in s.split() if t not in _NOISE_TOKENS and len(t) > 1]
    return " ".join(tokens)


def is_composite(raw: str) -> bool:
    """A bundle that should not map to a single recipe template.

    Either a '+' explicitly enumerates constituents, or a bundling keyword
    (COMBO, MEAL, BOX, FESTIVAL, …) signals a multi-item set.
    """
    up = (raw or "").upper()
    if any(h in up for h in _WASTAGE_HINT):
        return True
    if up.count("+") >= 1:
        return True
    return any(h in up for h in _COMPOSITE_HINTS)


def is_wastage(raw: str) -> bool:
    up = (raw or "").upper()
    return any(h in up for h in _WASTAGE_HINT)


def build_template_corpus(skus: pd.DataFrame) -> tuple[list[str], dict[str, str]]:
    corpus: list[str] = []
    corpus_to_sku: dict[str, str] = {}
    for _, row in skus.iterrows():
        sid = row["sku_id"]
        candidates = [row["name"]] + _TEMPLATE_ALIASES.get(sid, [])
        for c in candidates:
            n = normalise(c)
            if n:
                corpus.append(n)
                corpus_to_sku[n] = sid
    return corpus, corpus_to_sku


def band_for(score: float) -> str:
    for band, threshold in _BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return "unmapped"


def generate_candidates(db_path: Path, out_path: Path) -> dict:
    con = duckdb.connect(str(db_path), read_only=True)
    menu = con.execute(
        """
        SELECT product_id, product_name, base_name, category,
               units_sold, revenue_pkr
        FROM menu_items
        ORDER BY revenue_pkr DESC NULLS LAST
        """
    ).fetchdf()
    skus = con.execute(
        "SELECT sku_id, name, category, price_pkr FROM skus ORDER BY sku_id"
    ).fetchdf()
    con.close()

    corpus, corpus_to_sku = build_template_corpus(skus)
    sku_lookup = {row.sku_id: row for row in skus.itertuples()}

    rows: list[dict] = []
    total_rev = float(menu["revenue_pkr"].fillna(0).sum()) or 1.0

    for _, item in menu.iterrows():
        raw_name = item["product_name"] or ""
        base = item.get("base_name") or raw_name
        normalised = normalise(base)

        wastage = is_wastage(raw_name)
        composite = is_composite(raw_name) and not wastage

        if not normalised:
            best_sku, best_template_name, best_score = "", "", 0.0
        else:
            hit = process.extractOne(
                normalised, corpus, scorer=fuzz.WRatio
            )
            if hit is None:
                best_sku, best_template_name, best_score = "", "", 0.0
            else:
                matched_phrase, best_score, _ = hit
                best_sku = corpus_to_sku[matched_phrase]
                best_template_name = sku_lookup[best_sku].name

        if wastage:
            confidence_band = "exclude_wastage"
        elif composite:
            # Composite bundles always require manual decomposition — even when
            # one constituent matches a template, the dish is more than that.
            confidence_band = "composite_review"
        else:
            confidence_band = band_for(best_score)

        rev = float(item["revenue_pkr"] or 0.0)
        rows.append(
            {
                "pos_sku_id": item["product_id"],
                "pos_product_name": raw_name,
                "pos_base_name": base,
                "pos_category": item["category"],
                "units_sold": float(item["units_sold"] or 0.0),
                "revenue_pkr": rev,
                "revenue_share_pct": round(100.0 * rev / total_rev, 4),
                "recipe_template_id": best_sku,
                "recipe_template_name": best_template_name,
                "confidence_score": round(float(best_score), 2),
                "confidence_band": confidence_band,
                "is_composite": composite,
                "is_wastage": wastage,
                "match_notes": "",
                "approved_by_reviewer": False,
            }
        )

    df = pd.DataFrame(rows).sort_values(
        ["revenue_pkr"], ascending=False
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    summary = summarise(df, total_rev)
    return summary


def summarise(df: pd.DataFrame, total_rev: float) -> dict:
    band_counts = df["confidence_band"].value_counts().to_dict()
    band_revenue = df.groupby("confidence_band")["revenue_pkr"].sum().to_dict()
    mapped_bands = {"exact", "close", "approximate"}
    mapped_rev = sum(v for b, v in band_revenue.items() if b in mapped_bands)
    coverage = mapped_rev / total_rev if total_rev else 0.0

    top20_unmapped = (
        df[df["confidence_band"].isin({"unmapped", "composite_review"})]
        .head(20)[["pos_sku_id", "pos_product_name", "revenue_pkr",
                   "confidence_score", "confidence_band"]]
        .to_dict(orient="records")
    )

    return {
        "total_skus": len(df),
        "total_revenue_pkr": total_rev,
        "band_counts": band_counts,
        "band_revenue": band_revenue,
        "revenue_coverage_if_approved": coverage,
        "top20_unmapped_by_revenue": top20_unmapped,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    summary = generate_candidates(args.db, args.out)
    print(f"=== sku_recipe_mapping_candidates → {args.out} ===")
    print(f"total_skus: {summary['total_skus']}")
    print(f"total_revenue_pkr: {summary['total_revenue_pkr']:,.0f}")
    print("band_counts:")
    for band, n in sorted(summary["band_counts"].items(), key=lambda kv: -kv[1]):
        rev = summary["band_revenue"].get(band, 0.0)
        share = 100.0 * rev / summary["total_revenue_pkr"]
        print(f"  {band:<20} n={n:<4}  revenue={rev:>16,.0f}  share={share:>6.2f}%")
    print(f"revenue_coverage_if_approved (mapped bands): "
          f"{summary['revenue_coverage_if_approved']*100:.2f}%")
    print()
    print("top 20 unmapped / composite_review by revenue:")
    for r in summary["top20_unmapped_by_revenue"]:
        print(f"  {r['pos_sku_id']}  rev={r['revenue_pkr']:>14,.0f}  "
              f"score={r['confidence_score']:>5.1f}  {r['confidence_band']:<18}  "
              f"{r['pos_product_name']}")


if __name__ == "__main__":
    main()
