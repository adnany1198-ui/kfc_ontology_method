"""Streamlit entry point — Overview page. See SPEC.md §7.7."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from backend import api
from components import time_cursor_widget

DB_PATH = Path(__file__).parent / "data" / "kfc.duckdb"


def main() -> None:
    st.set_page_config(page_title="KFC Ontology", layout="wide")

    if not DB_PATH.exists():
        st.error(
            "Database not found. Run `python data/load.py` to bootstrap "
            "the DuckDB before launching the app."
        )
        st.stop()

    cur = time_cursor_widget.render()
    _provenance_summary_sidebar()

    st.title("KFC Ontology — Overview")
    st.caption(
        "Operational data → derived entities → credit products. "
        "Composability is the proof of architecture."
    )

    summary = api.get_data_layer_summary(cur)

    st.markdown("### Core claim")
    st.markdown(
        "Operating businesses like KFC Pakistan can be modelled as "
        "temporally-aligned event streams. The relationships *across* "
        "streams — once captured as **derived entities** — become the "
        "data layer for credit products that retrieval-and-aggregation "
        "BI cannot directly price. Every number on this site is "
        "decomposable to its source events."
    )

    st.markdown("### Notable numbers at cursor")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("POS transactions to date",
              f"{summary['observed_tx_to_date']:,}")
    c2.metric("POS revenue to date",
              f"PKR {summary['observed_revenue_to_date']/1e6:.1f}M")
    c3.metric("Outstanding AP (modelled)",
              f"PKR {summary['modelled_ap_outstanding']/1e6:.1f}M")
    c4.metric("Due next 7d (modelled)",
              f"PKR {summary['modelled_pay_next_7']/1e6:.1f}M")

    st.markdown("### Quick-jump")
    j1, j2, j3 = st.columns(3)
    with j1:
        st.page_link("pages/01_Data_Layer.py",
                     label="→ See the data layer", icon="📊")
    with j2:
        st.page_link("pages/02_Derived_Entities.py",
                     label="→ See derived entities", icon="🧮")
    with j3:
        st.page_link("pages/03_Credit_Products.py",
                     label="→ Simulate a credit product", icon="💳")


def _provenance_summary_sidebar() -> None:
    st.sidebar.markdown("### Provenance")
    summary = api.get_provenance_summary()
    total_rows = sum(v["rows"] for v in summary.values()) or 1
    for prov in ("observed", "derived", "modelled"):
        v = summary.get(prov, {"tables": 0, "rows": 0})
        share = 100 * v["rows"] / total_rows
        st.sidebar.markdown(
            f"- **{prov}**: {v['tables']} tables · {v['rows']:,} rows · "
            f"{share:.1f}%"
        )


if __name__ == "__main__":
    main()
