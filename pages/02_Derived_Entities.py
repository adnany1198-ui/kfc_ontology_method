"""Derived Entities page — OTS, SOY, DPI, CCC. See SPEC §7.3."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from backend import api
from components import provenance_badge, time_cursor_widget
from derived import REGISTRY

PROVENANCE = "derived"


def main() -> None:
    st.set_page_config(page_title="Derived Entities", layout="wide")
    cur = time_cursor_widget.render()

    st.title("Derived Entities")
    provenance_badge.render(PROVENANCE, f"computed at cursor {cur.date()}")

    tabs = st.tabs(["OTS", "SOY", "DPI", "CCC"])

    with tabs[0]:
        _section_ots(cur)
    with tabs[1]:
        _section_soy(cur)
    with tabs[2]:
        _section_dpi(cur)
    with tabs[3]:
        _section_ccc(cur)


def _section_ots(cur) -> None:
    st.subheader("OTS — Operational Trust Score")
    st.caption(
        "0.30·on-time + 0.20·fill + 0.25·quality + 0.15·volume-consistency "
        "+ 0.10·payment-compliance, last 90 days at cursor."
    )
    rows = _table_for("ots", cur)
    if rows.empty:
        st.info("No OTS values at cursor.")
        return
    tier_counts = rows["tier"].value_counts().to_dict()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("A-tier (≥0.92)", tier_counts.get("A", 0))
    c2.metric("B-tier (0.85–0.92)", tier_counts.get("B", 0))
    c3.metric("C-tier (0.78–0.85)", tier_counts.get("C", 0))
    c4.metric("D-tier (<0.78)", tier_counts.get("D", 0))
    st.dataframe(rows, hide_index=True, use_container_width=True)
    _drill(rows, "ots", cur)


def _section_soy(cur) -> None:
    st.subheader("SOY — Supplier Originatable Yield")
    st.caption(
        "Per-cycle discount × outstanding invoices, annualised, "
        "risk-adjusted by OTS (factor 0.5 per CLAUDE.md §4)."
    )
    rows = _table_for("soy", cur)
    if rows.empty:
        st.info("No SOY values at cursor.")
        return
    total = float(rows["value"].sum())
    outs = float(rows["outstanding_amount"].sum()) if "outstanding_amount" in rows else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("Annualised yield (sum)", f"PKR {total/1e6:.1f}M")
    c2.metric("Outstanding (sum)", f"PKR {outs/1e6:.1f}M")
    if outs > 0:
        c3.metric("Pool gross rate", f"{(total/outs)*100:.2f}%")
    st.dataframe(rows, hide_index=True, use_container_width=True)
    _drill(rows, "soy", cur)


def _section_dpi(cur) -> None:
    st.subheader("DPI — Demand Predictability Index")
    st.caption("1 − mean(|forecast − actual| / actual) over rolling SMA-30 horizons.")
    rows = _table_for("dpi", cur)
    if rows.empty:
        st.info("No DPI values at cursor.")
        return
    st.dataframe(rows, hide_index=True, use_container_width=True)
    _drill(rows, "dpi", cur)


def _section_ccc(cur) -> None:
    st.subheader("CCC — Cash Conversion Coefficient (system)")
    st.caption(
        "payment_terms_weighted_avg + settlement_latency + processing_overhead. "
        "Rail-sensitive."
    )
    cols = st.columns(3)
    for col, rail in zip(cols, ["bank", "raast", "stablecoin"]):
        r = REGISTRY["ccc"].compute("system", cur, rail=rail)
        with col:
            st.markdown(f"**{rail.upper()}**")
            st.metric("CCC days", f"{r.value:.1f}")
            st.metric("Daily COGS",
                      f"PKR {r.components['daily_cogs_pkr']/1e6:.2f}M")
            st.metric("Deployable float",
                      f"PKR {r.components['deployable_float_pkr']/1e9:.2f}B")
            st.caption(f"cogs_source: {r.components['cogs_source']}")
    bank = REGISTRY["ccc"].compute("system", cur, rail="bank")
    st.markdown("**Components (bank rail)**")
    st.json(bank.components)


def _table_for(entity_type: str, cur) -> pd.DataFrame:
    cls = REGISTRY[entity_type]
    rows = []
    for tid in cls.list_targets():
        r = cls.compute_cached(tid, cur)
        if isinstance(r.value, dict) and r.value.get("insufficient_data"):
            rows.append({"target": tid, "value": None,
                         **{k: None for k in r.components}, "_status": "n/a"})
            continue
        row = {"target": tid, "value": r.value,
               "computation_id": r.computation_id}
        row.update(r.components)
        rows.append(row)
    df = pd.DataFrame(rows)
    if "value" in df.columns:
        df = df.sort_values("value", ascending=False, na_position="last")
    return df


def _drill(rows: pd.DataFrame, entity_type: str, cur) -> None:
    targets = rows["target"].tolist()
    if not targets:
        return
    pick = st.selectbox(f"Drill into {entity_type.upper()} for target",
                        targets, key=f"drill_{entity_type}")
    cls = REGISTRY[entity_type]
    r = cls.compute_cached(pick, cur)
    st.markdown("**Components**")
    st.json(r.components)
    if r.computation_id:
        depth = st.slider("Decompose depth", 1, 4, 2,
                          key=f"depth_{entity_type}")
        st.markdown("**Lineage decomposition**")
        st.json(api.decompose(r.computation_id, depth=depth))


if __name__ == "__main__":
    main()
