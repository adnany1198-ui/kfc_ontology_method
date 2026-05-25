"""Generate sku_recipe_mapping_candidates.csv (CLAUDE.md Section 1, Phase 1 step 4).

One row per (real_sku, recipe_template) pair. Composite bundles emit multiple
rows — one per constituent — by parsing the enumeration embedded in the
product name (e.g. "XTREME DUO BOX (2 ZIN+2H&C+1LF+2RD)").

Bands:
  exact / close / approximate   — single-item fuzzy match
  composite_decomposed          — bundle parsed cleanly into templates
  composite_partial             — bundle parsed but some tokens have no template
  needs_manual_decomposition    — bundle name has no enumerated breakdown
  unmapped                      — single item with no plausible template
  exclude_wastage               — explicit (WASTAGE) / modifier rows

Halts at Gate 1: no DB write here. After Adnan edits the CSV, a follow-up
loads it into the sku_recipe_mapping table.
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

# Tokens dropped before fuzzy matching for single-item names.
_NOISE_TOKENS = {
    "ALACARTE", "ALA", "CARTE", "COMBO", "MEAL", "BOX", "BUCKET", "DEAL",
    "WITH", "AND", "FOR", "THE", "SET", "VALUE", "FAMILY", "WOW",
    "XTREME", "FEAST", "FESTIVAL", "SPECIAL", "PACK", "OFFER", "GOLOOTLO",
    "DRIVE", "THRU", "THORUGH", "DELIVERY", "EAT", "OUT",
    "TAKE", "AWAY",
}

# Words that indicate the dish is a bundle of multiple items rather than a
# single recipe template. Only words that are reliable bundle signals.
_COMPOSITE_KEYWORDS = (
    "FAMILY FESTIVAL", "MEAL BOX", "DUO BOX", "CRISPY BOX",
    "WOW", "FEAST", "BIRTHDAY DEAL", "GOLOOTLO", "CHARITY MEAL",
    "MIDNIGHT SPECIAL", "MIDNIGHT - 1", "MIDNIGHT 3",
    "MIGHTY BURGER COMBO", "ZINGER COMBO", "ZINGER STACKER COMBO",
    "TWISTER COMBO", "KRUNCH UP", "CHICKY MEAL", "CHICKEN CHIPS",
    "CHICKEN & RICE", "BONELESS (", "SNACK BUCKET", "VALUE BUCKET",
    "STRIPS, CHIPS", "KENTUCKY COMBO", "BOK DEAL", "XTREME DUO",
    "FF3", "XTREME BOX", "XTREME -", "MIGHTY COMBO",
)
_WASTAGE_HINT = ("WASTAGE", "MODIFIER")

# Manual aliases that help the single-item fuzzy matcher disambiguate.
_TEMPLATE_ALIASES: dict[str, list[str]] = {
    "SKU-001": ["ZINGER BURGER", "ZINGER ALACARTE"],
    "SKU-002": ["ZINGER STACKER", "STACKER BURGER"],
    "SKU-003": ["ZINGER JUNIOR", "JUNIOR ZINGER"],
    "SKU-004": ["MIGHTY ZINGER", "MIGHTY ZINGER BURGER"],
    "SKU-005": ["KRUNCH BURGER", "KRUNCH ALACARTE"],
    "SKU-010": ["HOT AND CRISPY 2 PCS", "H&C 2 PCS", "HOT CRISPY 2PC"],
    "SKU-011": ["HOT AND CRISPY 3 PCS", "H&C 3 PCS"],
    "SKU-012": ["HOT AND CRISPY 5 PCS", "H&C 5 PCS"],
    "SKU-013": ["HOT AND CRISPY 8 PCS BUCKET"],
    "SKU-014": ["HOT AND CRISPY 12 PCS BUCKET"],
    "SKU-015": ["HOT AND CRISPY 21 PCS BUCKET"],
    "SKU-020": ["HOT WINGS 6 PCS"],
    "SKU-021": ["HOT WINGS 12 PCS", "HOT WINGS 10 PCS"],
    "SKU-022": ["CHICKEN STRIPS 3 PCS"],
    "SKU-023": ["CHICKEN STRIPS 5 PCS", "CHICKEN STRIPS 4"],
    "SKU-030": ["TWISTER WRAP"],
    "SKU-031": ["CHICKEN SNACKER TWISTER"],
    "SKU-040": ["RICE AND SPICE", "RICE N SPICE", "RICE SPICE"],
    "SKU-041": ["BONELESS CHICKEN BUCKET"],
    "SKU-050": ["FRIES REGULAR", "FRENCH FRIES REGULAR"],
    "SKU-051": ["FRIES LARGE", "FRENCH FRIES LARGE"],
    "SKU-052": ["COLESLAW", "COLE SLAW"],
    "SKU-053": ["CORN ON THE COB"],
    "SKU-060": ["PEPSI REGULAR"],
    "SKU-061": ["PEPSI LARGE"],
    "SKU-062": ["7UP REGULAR"],
    "SKU-063": ["MOUNTAIN DEW REGULAR"],
    "SKU-064": ["MINERAL WATER"],
    "SKU-070": ["SOFT SERVE CONE", "ICE CREAM CONE"],
    "SKU-071": ["KRUSHER CHOCOLATE"],
    "SKU-072": ["KRUSHER STRAWBERRY"],
}

_BAND_THRESHOLDS = [("exact", 95.0), ("close", 80.0), ("approximate", 60.0)]


# Token → recipe template. None means the token is recognised but has no
# template (e.g. nuggets, dipping sauce — visible in the bundle but not in
# the seed recipe set).
_TOKEN_MAP: dict[str, str | None] = {
    # Burgers
    "ZIN": "SKU-001",
    "ZINGER": "SKU-001",
    "ZINGERBURGER": "SKU-001",
    "KRUNCH": "SKU-005",
    "MIG": "SKU-004",
    "MIGHTY": "SKU-004",
    "MIGHTYZINGER": "SKU-004",
    "STACKER": "SKU-002",
    "JUNIOR": "SKU-003",
    "KENTUCKYBURGER": "SKU-005",       # closest available burger
    # Hot & Crispy — count-dependent, resolved in code
    "H&C": "H_AND_C_BY_COUNT",
    "H&CCHICKEN": "H_AND_C_BY_COUNT",
    "PC": "H_AND_C_BY_COUNT",
    "PCS": "H_AND_C_BY_COUNT",
    "PIECES": "H_AND_C_BY_COUNT",
    "PIECE": "H_AND_C_BY_COUNT",
    "HOTANDCRISPY": "H_AND_C_BY_COUNT",
    # Strips — count-dependent
    "STRIPS": "STRIPS_BY_COUNT",
    "STRIP": "STRIPS_BY_COUNT",
    # Wings — count-dependent
    "WING": "WINGS_BY_COUNT",
    "WINGS": "WINGS_BY_COUNT",
    "HOTWING": "WINGS_BY_COUNT",
    "HOTWINGS": "WINGS_BY_COUNT",
    # Wraps
    "TWISTER": "SKU-030",
    "SNACKER": "SKU-031",
    # Sides
    "LF": "SKU-051",
    "RF": "SKU-050",
    "FRIES": "SKU-050",
    "FRENCHFRIES": "SKU-050",
    "CHICKYFRIES": "SKU-050",
    "COB": "SKU-053",
    "CORN": "SKU-053",
    "COLESLAW": "SKU-052",
    "COLELAW": "SKU-052",
    # Drinks — RD is "regular drink", DR is taken as "large drink"
    "RD": "SKU-060",
    "DR": "SKU-061",
    "FOUNTAIN": "SKU-060",
    "FOUNTAINDRINK": "SKU-060",
    "DRINK": "SKU-060",
    # Desserts
    "CONE": "SKU-070",
    "ICECREAM": "SKU-070",
    "ICECREAMCONE": "SKU-070",
    # Rice
    "RICE": "SKU-040",
    "RICESPICE": "SKU-040",
    # Known-but-not-in-recipes (visible bundle constituents w/o templates)
    "NUGGET": None,
    "NUGGETS": None,
    "HOTSHOT": None,
    "HOTSHOTS": None,
    "DIP": None,
    "DIPS": None,
    "SLICE": None,        # cheese slice
    "PRM": None,          # premium add-on
    "PARATHA": None,
}

# Drop-words inside enumeration bodies — these are decorative.
_BUNDLE_NOISE = {
    "AND", "WITH", "THE", "FOR", "A", "AN", "OF", "OR",
    "CHICKEN", "BURGER", "PRICE", "COMBO", "MEAL", "BUCKET", "BOX",
    "DEAL", "PACK", "BUNDLE", "CHIPS",   # bundle word, not a constituent
    "PC", "PCS", "PIECE", "PIECES",
}

# count → SKU for H&C, strips, wings.
_HC_BY_COUNT = {
    1: "SKU-010", 2: "SKU-010", 3: "SKU-011", 4: "SKU-011",
    5: "SKU-012", 6: "SKU-012", 7: "SKU-013", 8: "SKU-013",
    9: "SKU-013", 10: "SKU-014", 11: "SKU-014", 12: "SKU-014",
    15: "SKU-014", 21: "SKU-015",
}
_STRIPS_BY_COUNT = {1: "SKU-022", 2: "SKU-022", 3: "SKU-022",
                    4: "SKU-023", 5: "SKU-023", 6: "SKU-023"}
_WINGS_BY_COUNT = {1: "SKU-020", 2: "SKU-020", 3: "SKU-020", 4: "SKU-020",
                   5: "SKU-020", 6: "SKU-020",
                   7: "SKU-021", 8: "SKU-021", 9: "SKU-021", 10: "SKU-021",
                   11: "SKU-021", 12: "SKU-021"}


def normalise_single(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = name.upper()
    s = re.sub(r"[\(\)\[\]\{\}]", " ", s)
    s = re.sub(r"[^A-Z0-9& +]", " ", s)
    s = s.replace("&", " AND ")
    s = re.sub(r"\s+", " ", s).strip()
    tokens = [t for t in s.split() if t not in _NOISE_TOKENS and len(t) > 1]
    return " ".join(tokens)


def strip_channel(name: str) -> str:
    """Remove channel + 'Alacarte' tail, keep the dish portion."""
    return re.sub(
        r"\s*(EAT\s*IN|EAT\s*OUT|DRIVE\s*THRU|DRIVE\s*THORUGH|"
        r"TAKE\s*AWAY|DELIVERY)\b\s*-?\s*(ALACARTE|ALA\s*CARTE)?\s*",
        " ",
        name or "",
        flags=re.IGNORECASE,
    ).strip(" -")


def is_wastage(raw: str) -> bool:
    up = (raw or "").upper()
    return any(h in up for h in _WASTAGE_HINT)


def is_composite(raw: str) -> bool:
    """A bundle that should not collapse to a single recipe template."""
    up = (raw or "").upper()
    if is_wastage(raw):
        return False  # handled separately
    if "+" in up:
        return True
    return any(k in up for k in _COMPOSITE_KEYWORDS)


def has_enumeration(raw: str) -> bool:
    """Does the bundle name spell out its constituents?"""
    up = (raw or "").upper()
    if "+" in up:
        return True
    inside = re.findall(r"\(([^)]*)\)", up)
    for body in inside:
        # count-token pairs (with optional space) — parens are intentional
        # enumeration, so a single pair is enough.
        if re.search(r"\b\d+\s*[A-Z&]{2,}", body):
            return True
    # outside-of-parens enumeration: require ≥2 count-token pairs.
    pairs = re.findall(r"\b\d+\s*[A-Z&]{2,}", up)
    return len(pairs) >= 2


def _bundle_body(raw: str) -> str:
    """Return the enumeration body — parens content if present, else the
    whole stripped name."""
    up = strip_channel(raw or "").upper()
    parens = re.findall(r"\(([^)]*)\)", up)
    if parens:
        for body in parens:
            if "+" in body or re.search(r"\d", body):
                return body
        return parens[0]
    # Common pattern: `(...` with no closing paren (POS data is sloppy).
    open_only = re.search(r"\(([^()]*)$", up)
    if open_only and ("+" in open_only.group(1) or re.search(r"\d", open_only.group(1))):
        return open_only.group(1)
    return up


_COUNT_TOKEN_RE = re.compile(r"(\d+)\s*([A-Z&]+(?:\s+[A-Z&]+)?)")
_BARE_TOKEN_RE = re.compile(r"([A-Z&]+(?:\s+[A-Z&]+)?)")


def _normalise_token(tok: str) -> str:
    tok = tok.upper().replace(" ", "").replace("PCS", "PC").rstrip("S")
    # collapse alternative spellings
    tok = tok.replace("HOTANDCRISPY", "H&C")
    return tok


def _lookup_token(tok: str, count: int) -> tuple[str | None, str | None]:
    """Return (recipe_template_id, note). recipe_template_id may be None for
    known-but-not-mappable tokens (e.g. NUGGETS)."""
    norm = _normalise_token(tok)
    # Try direct lookups, peeling final 'S'.
    candidates = [norm, norm.rstrip("S"), norm + "S"]
    for c in candidates:
        if c in _TOKEN_MAP:
            sku = _TOKEN_MAP[c]
            if sku == "H_AND_C_BY_COUNT":
                resolved = _HC_BY_COUNT.get(count)
                if resolved is None:
                    return _HC_BY_COUNT[max(_HC_BY_COUNT)], (
                        f"H&C count {count} not in template grid — "
                        f"using SKU-015 (21pc)"
                    )
                return resolved, None
            if sku == "STRIPS_BY_COUNT":
                return _STRIPS_BY_COUNT.get(count, "SKU-023"), None
            if sku == "WINGS_BY_COUNT":
                return _WINGS_BY_COUNT.get(count, "SKU-021"), None
            return sku, None
    return None, "unrecognised"


def parse_bundle(raw: str) -> tuple[list[dict], list[str]]:
    """Return (constituents, unparsed_tokens).

    Constituents: [{template_id, quantity, source_token, note}].
    Empty list when nothing parseable.
    """
    body = _bundle_body(raw)
    body = body.replace(",", " ").replace("/", " ")
    body = re.sub(r"\bPRICE\s*\d+\b", " ", body)
    body = re.sub(r"\s+", " ", body).strip()

    parts: list[str]
    if "+" in body:
        parts = [p.strip() for p in body.split("+") if p.strip()]
    else:
        # extract count-token pairs across the whole body
        parts = []
        for m in re.finditer(r"\d+\s*[A-Z&]+(?:\s+[A-Z&]+)?", body):
            parts.append(m.group())

    aggregated: dict[str, dict] = {}
    unparsed: list[str] = []

    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = _COUNT_TOKEN_RE.match(part)
        if m:
            count = int(m.group(1))
            tok_raw = m.group(2)
        else:
            count = 1
            mb = _BARE_TOKEN_RE.search(part)
            if not mb:
                unparsed.append(part)
                continue
            tok_raw = mb.group(1)

        tok_clean = tok_raw.upper().strip()
        # split multi-word tokens — e.g. "H&C CHICKEN" → take leading meaningful piece
        words = [w for w in tok_clean.split() if w not in _BUNDLE_NOISE]
        candidate_token = "".join(words) if words else tok_clean.replace(" ", "")

        if not candidate_token:
            continue

        sku, note = _lookup_token(candidate_token, count)
        if sku is None and note == "unrecognised":
            unparsed.append(f"{count}×{tok_raw}")
            continue
        if sku is None:
            # Known-but-not-mappable (nuggets, dip etc.)
            unparsed.append(f"{count}×{candidate_token}(no-template)")
            continue

        key = sku
        if key in aggregated:
            aggregated[key]["quantity"] += count
            if note and note not in aggregated[key]["note"]:
                aggregated[key]["note"] += f"; {note}"
        else:
            aggregated[key] = {
                "template_id": sku,
                "quantity": count,
                "source_token": f"{count}×{candidate_token}",
                "note": note or "",
            }

    return list(aggregated.values()), unparsed


def build_template_corpus(skus: pd.DataFrame) -> tuple[list[str], dict[str, str]]:
    corpus: list[str] = []
    corpus_to_sku: dict[str, str] = {}
    for _, row in skus.iterrows():
        sid = row["sku_id"]
        candidates = [row["name"]] + _TEMPLATE_ALIASES.get(sid, [])
        for c in candidates:
            n = normalise_single(c)
            if n:
                corpus.append(n)
                corpus_to_sku[n] = sid
    return corpus, corpus_to_sku


def band_for(score: float) -> str:
    for band, threshold in _BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return "unmapped"


def build_rows(menu: pd.DataFrame, skus: pd.DataFrame) -> pd.DataFrame:
    corpus, corpus_to_sku = build_template_corpus(skus)
    sku_lookup = {row.sku_id: row for row in skus.itertuples()}

    rows: list[dict] = []

    for _, item in menu.iterrows():
        raw_name = item["product_name"] or ""
        base = item.get("base_name") or raw_name
        rev = float(item["revenue_pkr"] or 0.0)
        units = float(item["units_sold"] or 0.0)

        # 1. Wastage / modifiers — exclude entirely.
        if is_wastage(raw_name):
            rows.append(_row(item, "", "", 0.0, "exclude_wastage",
                             "primary", "wastage / modifier line — exclude"))
            continue

        composite = is_composite(raw_name)

        # 2. Single items — fuzzy match against templates.
        if not composite:
            normalised = normalise_single(strip_channel(base))
            if not normalised:
                rows.append(_row(item, "", "", 0.0, "unmapped",
                                 "primary", "empty normalised name"))
                continue
            hit = process.extractOne(normalised, corpus, scorer=fuzz.WRatio)
            if hit is None:
                rows.append(_row(item, "", "", 0.0, "unmapped",
                                 "primary", ""))
                continue
            matched_phrase, score, _ = hit
            sku = corpus_to_sku[matched_phrase]
            band = band_for(score)
            tmpl_name = sku_lookup[sku].name if band != "unmapped" else ""
            rows.append(_row(item, sku if band != "unmapped" else "",
                             tmpl_name, 1.0, band, "primary",
                             f"fuzzy WRatio={score:.1f}"))
            continue

        # 3. Composite bundles.
        if not has_enumeration(raw_name):
            rows.append(_row(item, "", "", 0.0,
                             "needs_manual_decomposition", "primary",
                             "bundle name has no enumerated breakdown"))
            continue

        constituents, unparsed = parse_bundle(raw_name)
        if not constituents:
            rows.append(_row(item, "", "", 0.0,
                             "needs_manual_decomposition", "primary",
                             "enumeration present but no parseable tokens"))
            continue

        band = "composite_decomposed" if not unparsed else "composite_partial"
        unparsed_note = (
            f"unparsed tokens: {', '.join(unparsed)}" if unparsed else ""
        )
        for c in constituents:
            tmpl_name = sku_lookup[c["template_id"]].name
            parts = [p for p in [c["note"], unparsed_note] if p]
            note = "; ".join(parts) if parts else f"parsed from '{c['source_token']}'"
            rows.append(_row(item, c["template_id"], tmpl_name,
                             float(c["quantity"]), band, "constituent", note))

    df = pd.DataFrame(rows)
    return df


def _row(item, template_id, template_name, quantity, band, role, note) -> dict:
    return {
        "real_sku_id": item["product_id"],
        "real_sku_name": item["product_name"],
        "pos_base_name": item.get("base_name"),
        "pos_category": item["category"],
        "units_sold": float(item["units_sold"] or 0.0),
        "revenue_pkr": float(item["revenue_pkr"] or 0.0),
        "recipe_template_id": template_id,
        "recipe_template_name": template_name,
        "quantity": quantity,
        "confidence_band": band,
        "component_role": role,
        "note": note,
        "approved_by_reviewer": False,
    }


def summarise(df: pd.DataFrame) -> dict:
    # Coverage is measured per real-SKU, not per row: a SKU is "covered" if
    # it has at least one mapped row (any band except unmapped /
    # needs_manual / exclude_wastage).
    mapped_bands = {"exact", "close", "approximate",
                    "composite_decomposed", "composite_partial"}
    per_sku = (
        df.groupby("real_sku_id")
        .agg(
            revenue_pkr=("revenue_pkr", "first"),
            real_sku_name=("real_sku_name", "first"),
            band=("confidence_band", "first"),
        )
        .reset_index()
    )
    total_rev = float(per_sku["revenue_pkr"].sum()) or 1.0
    band_counts = per_sku["band"].value_counts().to_dict()
    band_revenue = per_sku.groupby("band")["revenue_pkr"].sum().to_dict()
    mapped_rev = sum(v for b, v in band_revenue.items() if b in mapped_bands)
    coverage = mapped_rev / total_rev

    top_needs_manual = (
        per_sku[per_sku["band"] == "needs_manual_decomposition"]
        .nlargest(15, "revenue_pkr")[["real_sku_id", "real_sku_name", "revenue_pkr"]]
        .to_dict(orient="records")
    )
    top_unmapped = (
        per_sku[per_sku["band"] == "unmapped"]
        .nlargest(15, "revenue_pkr")[["real_sku_id", "real_sku_name", "revenue_pkr"]]
        .to_dict(orient="records")
    )
    top_partial = (
        per_sku[per_sku["band"] == "composite_partial"]
        .nlargest(15, "revenue_pkr")[["real_sku_id", "real_sku_name", "revenue_pkr"]]
        .to_dict(orient="records")
    )
    return {
        "total_real_skus": len(per_sku),
        "total_rows": len(df),
        "total_revenue_pkr": total_rev,
        "band_counts": band_counts,
        "band_revenue": band_revenue,
        "revenue_coverage_if_approved": coverage,
        "top_needs_manual_by_revenue": top_needs_manual,
        "top_unmapped_by_revenue": top_unmapped,
        "top_partial_by_revenue": top_partial,
    }


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

    df = build_rows(menu, skus)
    df = df.sort_values(["revenue_pkr", "real_sku_id", "component_role"],
                        ascending=[False, True, True])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return summarise(df)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    s = generate_candidates(args.db, args.out)
    print(f"=== sku_recipe_mapping_candidates → {args.out} ===")
    print(f"total_real_skus: {s['total_real_skus']}   total_rows: {s['total_rows']}")
    print(f"total_revenue_pkr: {s['total_revenue_pkr']:,.0f}")
    print("band_counts (per real SKU):")
    for band, n in sorted(s["band_counts"].items(), key=lambda kv: -kv[1]):
        rev = s["band_revenue"].get(band, 0.0)
        share = 100.0 * rev / s["total_revenue_pkr"]
        print(f"  {band:<32} n={n:<4}  revenue={rev:>16,.0f}  share={share:>6.2f}%")
    print(f"revenue_coverage_if_approved (mapped bands): "
          f"{s['revenue_coverage_if_approved']*100:.2f}%")

    def _dump(label, items):
        if not items:
            return
        print()
        print(label)
        for r in items:
            print(f"  {r['real_sku_id']}  rev={r['revenue_pkr']:>14,.0f}  "
                  f"{r['real_sku_name']}")

    _dump("top needs_manual_decomposition by revenue:",
          s["top_needs_manual_by_revenue"])
    _dump("top composite_partial by revenue:",
          s["top_partial_by_revenue"])
    _dump("top unmapped by revenue:", s["top_unmapped_by_revenue"])


if __name__ == "__main__":
    main()
