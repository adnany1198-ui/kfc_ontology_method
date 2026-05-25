"""About page — what's real, what's synthetic, methodology brief. See SPEC §7.8."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from backend import api
from backend.db import get_connection
from components import time_cursor_widget


def main() -> None:
    st.set_page_config(page_title="About", layout="wide")
    time_cursor_widget.render()

    st.title("About")

    st.markdown("## What this prototype is testing")
    st.markdown(
        "The hypothesis is that operating businesses like KFC Pakistan can be "
        "modelled as **temporally-aligned event streams**, and that the "
        "relationships *across* those streams — captured as **derived "
        "entities** — become the data layer for credit products that "
        "retrieval-and-aggregation BI cannot directly price. "
        "This prototype demonstrates the methodology end-to-end on real "
        "KFC PK POS data plus a modelled supply chain."
    )
    st.markdown(
        "Whether this architectural pattern delivers enough value to justify "
        "itself, relative to extending existing integrated platforms, is the "
        "question this prototype attempts to surface — it is not yet "
        "answered."
    )

    st.markdown("## What's real vs synthetic")
    con = get_connection(read_only=True)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY table_name"
        ).fetchall()]
        rows = []
        for t in tables:
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            rows.append({"table": t, "rows": n,
                         "provenance": api.get_provenance(t)})
    finally:
        con.close()
    st.dataframe(pd.DataFrame(rows), hide_index=True,
                 use_container_width=True)

    st.markdown("## Five example insights this enables")
    st.markdown(
        "- **Per-SKU true margin including supplier-cost drift** — POS × "
        "procurement-price history × recipe BOM, aligned at the moment of "
        "sale. *See Data Layer page → derived column.*"
    )
    st.markdown(
        "- **Supplier reliability as a continuously-updating signal** — "
        "OTS composed from delivery, quality, and payment streams. "
        "*See Derived Entities page → OTS tab.*"
    )
    st.markdown(
        "- **Demand-driven supplier cashflow inference** — outstanding "
        "receivables back-projected from the buyer's invoice and payment "
        "streams. *See SOY tab.*"
    )
    st.markdown(
        "- **Promotion ↔ supply-chain alignment** — cross-reference "
        "promotional calendar, POS uplift, and delivery schedule at the day "
        "grain (data layer panels)."
    )
    st.markdown(
        "- **Working-capital responsiveness to settlement rails** — same "
        "operational data, different CCC depending on the rail. "
        "*See Credit Products → Securitised Yield Originator → settlement "
        "rail comparison.*"
    )

    st.markdown("## What this is not claiming")
    st.markdown(
        "The numbers produced are computed against substantially synthetic "
        "supply-chain data. They are directionally plausible, not actual. "
        "The point is the methodology — when real procurement data replaces "
        "the modelled tables, the same architecture produces real numbers "
        "with the same structure."
    )

    st.markdown("## What data would convert modelled → observed")
    st.markdown(
        "- Real receiving logs (replace `deliveries`)\n"
        "- Real supplier invoice records (replace `invoices`)\n"
        "- Real procurement orders and prices (replace `purchase_orders`)\n"
        "- Real payment-run records (replace `payments`)\n"
        "- Real recipe BOM from KFC PK ops (replace `recipes`)"
    )

    st.markdown("## Known limitations and gaps")
    st.markdown(
        "- **Store ID mismatch**: synthetic seed uses `S-XXXX` format; real "
        "POS uses 4-digit zero-padded IDs. All real stores default-routed "
        "to commissary `COM-KHI-01`.\n"
        "- **Date alignment**: synthetic supply chain was generated for "
        "2025; shifted forward 14 months to overlap the 2026 POS window. "
        "Cadence patterns predate Ramadan/Eid 2026.\n"
        "- **Recipe coverage**: 99.23% of POS revenue maps. The residual "
        "0.77% (mostly sauces / tea / nuggets without a template) does not "
        "propagate to ingredient consumption.\n"
        "- **DPI**: SMA-30 forecasts diverge over 60/90-day horizons, so "
        "DPI values run low (0.23–0.27 for suppliers with enough PO "
        "history). Threshold defaults lowered accordingly.\n"
        "- **OTS A-tier**: no supplier hits ≥0.92 at the cursor — the spec "
        "thresholds were calibrated for cleaner data than the synthetic "
        "deliveries produce after quality-variance injection.\n"
        "- **Composability scope**: user entities are target-scoped only "
        "(v1); system-wide composition deferred.\n"
        "- **Performance**: no precompute / scheduled refresh. "
        "Cursor moves trigger on-demand recomputation with caching."
    )


if __name__ == "__main__":
    main()
