"""Pull real POS from the Railway endpoint into DuckDB.

Source contract: CLAUDE.md Section 1.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd
import requests

RAILWAY_BASE = "https://cv2-production-008f.up.railway.app"
TX_ENDPOINT = f"{RAILWAY_BASE}/transactions"
ROOT_ENDPOINT = f"{RAILWAY_BASE}/"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE = REPO_ROOT / "data" / ".pos_cache.json"
# Older runs cached here; we still read it if present so existing dev
# machines don't re-download.
_LEGACY_CACHE = REPO_ROOT / "data" / "raw_pos_cache" / "pos_transactions.json"
DEFAULT_DB = REPO_ROOT / "data" / "kfc.duckdb"

BASKET_MIN = 0.0
BASKET_MAX = 50_000.0
QTY_MIN = 1
QTY_MAX = 100

# Streaming download tunables (CLAUDE.md §1, Railway often truncates).
_FETCH_MAX_ATTEMPTS = 5
_FETCH_BACKOFF_BASE = 2.0
_FETCH_CHUNK_BYTES = 256 * 1024

_CHANNEL_PATTERNS = [
    (re.compile(r"\bDRIVE[ \-]?TH(?:R|OR)O?UGH\b", re.IGNORECASE), "DRIVE_THRU"),
    (re.compile(r"\bDRIVE\s*THRU\b", re.IGNORECASE), "DRIVE_THRU"),
    (re.compile(r"\bTAKE[ \-]?AWAY\b", re.IGNORECASE), "TAKE_AWAY"),
    (re.compile(r"\bEAT\s*IN\b", re.IGNORECASE), "EAT_IN"),
    (re.compile(r"\bEAT\s*OUT\b", re.IGNORECASE), "EAT_OUT"),
    (re.compile(r"\bDELIVERY\b", re.IGNORECASE), "DELIVERY"),
]


def extract_channel(name: str | None) -> tuple[str, str | None]:
    if not name:
        return name or "", None
    for pat, label in _CHANNEL_PATTERNS:
        m = pat.search(name)
        if m:
            base = (name[: m.start()] + name[m.end() :]).strip()
            base = re.sub(r"\s+", " ", base).strip(" -")
            return base, label
    return name.strip(), None


def _validate_json_file(path: Path) -> list[dict] | None:
    """Return parsed payload if the file is a complete JSON list, else None."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        with path.open() as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, list):
        return None
    return payload


def _stream_to_partial(url: str, partial_path: Path) -> int:
    """Download URL into a `.partial` file via chunked GET. Returns bytes written."""
    partial_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with requests.get(url, timeout=(30, 600), stream=True) as resp:
        resp.raise_for_status()
        expected = resp.headers.get("content-length")
        with partial_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=_FETCH_CHUNK_BYTES):
                if not chunk:
                    continue
                f.write(chunk)
                written += len(chunk)
        if expected is not None:
            expected_int = int(expected)
            if written != expected_int:
                raise IOError(
                    f"truncated download: got {written} bytes, "
                    f"server announced {expected_int}"
                )
    return written


def fetch_transactions(cache_path: Path, force: bool = False) -> list[dict]:
    # 1. Cache hit — trust the file if it parses as a JSON list. Also
    #    accept the legacy path so existing dev machines don't re-download.
    if not force:
        for candidate in (cache_path, _LEGACY_CACHE):
            cached = _validate_json_file(candidate)
            if cached is not None:
                print(f"[pos] cache hit {candidate} "
                      f"({candidate.stat().st_size/1e6:.1f} MB, "
                      f"{len(cached):,} records)")
                return cached
        if cache_path.exists():
            print(f"[pos] cache present but invalid — re-fetching")

    # 2. Streaming download with retry-on-incomplete + backoff. Writes to
    #    a `.partial` sibling and only swaps in once the file parses.
    partial_path = cache_path.with_suffix(cache_path.suffix + ".partial")
    last_error: Exception | None = None
    for attempt in range(1, _FETCH_MAX_ATTEMPTS + 1):
        try:
            if partial_path.exists():
                partial_path.unlink()
            print(f"[pos] fetching {TX_ENDPOINT} "
                  f"(attempt {attempt}/{_FETCH_MAX_ATTEMPTS})")
            written = _stream_to_partial(TX_ENDPOINT, partial_path)
            print(f"[pos]   downloaded {written/1e6:.1f} MB → "
                  f"{partial_path.name}; validating JSON…")
            payload = _validate_json_file(partial_path)
            if payload is None:
                raise IOError("payload did not parse as a JSON list")
            partial_path.replace(cache_path)
            print(f"[pos] cached {len(payload):,} records → {cache_path}")
            return payload
        except (requests.exceptions.RequestException, IOError,
                json.JSONDecodeError) as e:
            last_error = e
            print(f"[pos]   attempt {attempt} failed: "
                  f"{type(e).__name__}: {e}", file=sys.stderr)
            if attempt < _FETCH_MAX_ATTEMPTS:
                delay = _FETCH_BACKOFF_BASE ** attempt
                print(f"[pos]   backing off {delay:.0f}s…", file=sys.stderr)
                time.sleep(delay)
    raise RuntimeError(
        f"failed to fetch {TX_ENDPOINT} after {_FETCH_MAX_ATTEMPTS} attempts; "
        f"last error: {last_error}"
    )


def adopt_cache(cache_path: Path, source: Path) -> None:
    """If a one-shot fetch lives elsewhere on disk, move it into the cache slot."""
    if cache_path.exists() or not source.exists():
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    source.replace(cache_path)


def build_frames(records: Iterable[dict]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    tx_rows: list[dict] = []
    li_rows: list[dict] = []
    stats = {
        "raw": 0,
        "drop_duplicate_tx": 0,
        "drop_basket_range": 0,
        "drop_no_store": 0,
        "drop_no_timestamp": 0,
        "drop_no_lines": 0,
        "drop_line_qty": 0,
        "kept_tx": 0,
        "kept_lines": 0,
    }

    # Dedupe by transaction_id, keeping the record with the highest server-side id.
    dedup: dict[str, dict] = {}
    seen = 0
    for rec in records:
        seen += 1
        tid = rec.get("transaction_id")
        if not tid:
            continue
        prev = dedup.get(tid)
        if prev is None or (rec.get("id") or 0) > (prev.get("id") or 0):
            dedup[tid] = rec
    stats["drop_duplicate_tx"] = seen - len(dedup)

    for rec in dedup.values():
        stats["raw"] += 1
        store_id = rec.get("store_id")
        ts = rec.get("timestamp")
        bv = rec.get("basket_value")
        if store_id is None:
            stats["drop_no_store"] += 1
            continue
        if ts is None:
            stats["drop_no_timestamp"] += 1
            continue
        if bv is None or bv <= BASKET_MIN or bv >= BASKET_MAX:
            stats["drop_basket_range"] += 1
            continue
        lines = rec.get("line_items") or []
        if not lines:
            stats["drop_no_lines"] += 1
            continue

        kept_lines = []
        for idx, li in enumerate(lines):
            qty = li.get("quantity")
            if qty is None or qty < QTY_MIN or qty > QTY_MAX:
                stats["drop_line_qty"] += 1
                continue
            base_name, channel = extract_channel(li.get("product_name"))
            kept_lines.append(
                {
                    "transaction_id": rec["transaction_id"],
                    "line_no": idx,
                    "product_id": li.get("product_id"),
                    "product_name": li.get("product_name"),
                    "base_name": base_name,
                    "category": li.get("category"),
                    "channel": channel,
                    "quantity": float(qty),
                    "unit_price": float(li.get("unit_price") or 0.0),
                    "line_total": float(li.get("line_total") or 0.0),
                }
            )
        if not kept_lines:
            stats["drop_no_lines"] += 1
            continue

        tx_rows.append(
            {
                "transaction_id": rec["transaction_id"],
                "store_id": store_id,
                "till_id": rec.get("till_id"),
                "operator_id": rec.get("operator_id"),
                "transaction_timestamp": ts,
                "received_at": rec.get("received_at"),
                "basket_value": float(bv),
                "item_count": float(rec.get("item_count") or 0.0),
                "payment_method": rec.get("payment_method"),
                "line_count": len(kept_lines),
            }
        )
        li_rows.extend(kept_lines)
        stats["kept_tx"] += 1
        stats["kept_lines"] += len(kept_lines)

    tx_df = pd.DataFrame(tx_rows)
    li_df = pd.DataFrame(li_rows)
    tx_df["transaction_timestamp"] = pd.to_datetime(
        tx_df["transaction_timestamp"], utc=True, errors="coerce"
    ).dt.tz_convert(None)
    # propagate timestamp + store onto line items for cursor-time queries
    li_df = li_df.merge(
        tx_df[["transaction_id", "transaction_timestamp", "store_id"]],
        on="transaction_id",
        how="left",
    )
    return tx_df, li_df, stats


def load_into_duckdb(db_path: Path, tx_df: pd.DataFrame, li_df: pd.DataFrame) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        con.execute("DROP TABLE IF EXISTS pos_line_items")
        con.execute("DROP TABLE IF EXISTS pos_transactions")
        con.execute("DROP TABLE IF EXISTS menu_items")
        con.execute("DROP TABLE IF EXISTS store_summary")

        con.register("tx_df", tx_df)
        con.execute(
            """
            CREATE TABLE pos_transactions AS
            SELECT
              transaction_id,
              store_id,
              till_id,
              operator_id,
              transaction_timestamp,
              received_at,
              basket_value,
              item_count,
              payment_method,
              line_count,
              'observed' AS provenance
            FROM tx_df
            """
        )
        con.unregister("tx_df")

        con.register("li_df", li_df)
        con.execute(
            """
            CREATE TABLE pos_line_items AS
            SELECT
              transaction_id,
              line_no,
              product_id,
              product_name,
              base_name,
              category,
              channel,
              quantity,
              unit_price,
              line_total,
              transaction_timestamp,
              store_id,
              'observed' AS provenance
            FROM li_df
            """
        )
        con.unregister("li_df")

        con.execute(
            """
            CREATE TABLE menu_items AS
            WITH pid_stats AS (
              SELECT
                product_id,
                product_name,
                base_name,
                category,
                COUNT(*) AS occurrences
              FROM pos_line_items
              GROUP BY product_id, product_name, base_name, category
            ),
            pid_pick AS (
              SELECT
                product_id,
                FIRST(product_name ORDER BY occurrences DESC) AS product_name,
                FIRST(base_name ORDER BY occurrences DESC) AS base_name,
                FIRST(category ORDER BY occurrences DESC) AS category
              FROM pid_stats
              GROUP BY product_id
            )
            SELECT
              p.product_id,
              p.product_name,
              p.base_name,
              p.category,
              agg.units_sold,
              agg.revenue_pkr,
              agg.channels,
              'observed' AS provenance
            FROM pid_pick p
            LEFT JOIN (
              SELECT
                product_id,
                SUM(quantity) AS units_sold,
                SUM(line_total) AS revenue_pkr,
                LIST(DISTINCT channel) AS channels
              FROM pos_line_items
              GROUP BY product_id
            ) agg USING(product_id)
            """
        )

        con.execute(
            """
            CREATE TABLE store_summary AS
            SELECT
              store_id,
              COUNT(*) AS transactions,
              SUM(basket_value) AS revenue_pkr,
              MIN(transaction_timestamp) AS first_seen,
              MAX(transaction_timestamp) AS last_seen,
              'observed' AS provenance
            FROM pos_transactions
            GROUP BY store_id
            ORDER BY revenue_pkr DESC
            """
        )

        n_tx = con.execute("SELECT COUNT(*) FROM pos_transactions").fetchone()[0]
        n_li = con.execute("SELECT COUNT(*) FROM pos_line_items").fetchone()[0]
        n_mi = con.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
        n_st = con.execute("SELECT COUNT(*) FROM store_summary").fetchone()[0]
        print(f"[pos] loaded: pos_transactions={n_tx:,} pos_line_items={n_li:,} "
              f"menu_items={n_mi} store_summary={n_st}")
    finally:
        con.close()


def status() -> dict:
    return requests.get(ROOT_ENDPOINT, timeout=30).json()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--force", action="store_true", help="Force re-fetch")
    parser.add_argument("--adopt", type=Path, help="Move an existing JSON dump into the cache slot")
    args = parser.parse_args(argv)

    if args.adopt:
        adopt_cache(args.cache, args.adopt)

    st = status()
    print(f"[pos] receiver status={st.get('status')} server_count={st.get('transactions'):,}")

    records = fetch_transactions(args.cache, force=args.force)
    tx_df, li_df, stats = build_frames(records)
    print(f"[pos] quality filter: {stats}")
    load_into_duckdb(args.db, tx_df, li_df)


if __name__ == "__main__":
    main()
