"""Drill-down page — guided composability walk on Big Bird (SUP-001).

See SPEC §7.6 / CLAUDE.md §7. The walk path is hardcoded; values are
computed live at the cursor.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from backend import api
from backend.db import get_connection
from components import provenance_badge, time_cursor_widget
from derived import REGISTRY
from products import REGISTRY as PRODUCT_REGISTRY

REPRESENTATIVE = "SUP-001"


def main() -> None:
    st.set_page_config(page_title="Drill-down", layout="wide")
    cur = time_cursor_widget.render()

    st.title("Drill-down — Big Bird Foods (SUP-001)")
    st.caption(
        "A guided walk from a credit-product output down to specific "
        "delivery events at the modelled supply-chain ring. Every step is "
        "live at the cursor."
    )

    cif = PRODUCT_REGISTRY["captive_invoice_financing"]
    sim = cif.simulate({}, cur)
    sup_outcome = next(
        (o for o in sim.per_target_outcomes if o["target_id"] == REPRESENTATIVE),
        None,
    )

    step = st.session_state.setdefault("drill_step", 1)
    cols = st.columns([3, 1])
    with cols[1]:
        st.markdown("**Walk controls**")
        if st.button("← step back", disabled=step == 1):
            st.session_state["drill_step"] = max(1, step - 1)
            st.rerun()
        if st.button("step forward →", disabled=step == 5):
            st.session_state["drill_step"] = min(5, step + 1)
            st.rerun()
        if st.button("reset"):
            st.session_state["drill_step"] = 1
            st.rerun()

    with cols[0]:
        _step1(sim)
        if step >= 2:
            _step2(sim, sup_outcome)
        if step >= 3:
            _step3(sup_outcome, cur)
        if step >= 4:
            _step4(cur)
        if step >= 5:
            _step5(cur)


def _step1(sim) -> None:
    st.markdown("---")
    st.subheader("1 · Captive Invoice Financing total yield")
    provenance_badge.render("derived", "credit product simulation")
    m = sim.aggregate_metrics
    st.metric(
        "Total yield (annualised)",
        f"PKR {m['total_yield_annualised_pkr']/1e6:.1f}M",
        delta=f"{m['n_eligible']} of {m['n_eligible']+m['n_excluded']} suppliers eligible",
    )


def _step2(sim, sup_outcome) -> None:
    st.markdown("---")
    st.subheader("2 · Composed across eligible suppliers — Big Bird's contribution")
    df = pd.DataFrame(sim.per_target_outcomes).sort_values(
        "contribution_amount", ascending=False)
    st.dataframe(df, hide_index=True, use_container_width=True)
    if sup_outcome:
        st.success(
            f"Big Bird (SUP-001) contributes "
            f"**PKR {sup_outcome['contribution_amount']/1e6:.2f}M** annualised "
            f"on **PKR {sup_outcome['outstanding_pkr']/1e6:.1f}M** outstanding."
        )
    else:
        st.warning("Big Bird is not eligible at the current parameters.")


def _step3(sup_outcome, cur) -> None:
    st.markdown("---")
    st.subheader("3 · Big Bird's contribution decomposed")
    if not sup_outcome:
        st.info("Step 3 requires Big Bird to be eligible — try lowering the score threshold.")
        return
    soy = REGISTRY["soy"].compute_cached(REPRESENTATIVE, cur)
    ots = REGISTRY["ots"].compute_cached(REPRESENTATIVE, cur)
    c1, c2, c3 = st.columns(3)
    c1.metric("OTS score",
              f"{ots.value:.3f}" if isinstance(ots.value, (int, float)) else "n/a",
              delta=ots.components.get("tier"))
    c2.metric("Outstanding (PKR)",
              f"{soy.components.get('outstanding_amount', 0)/1e6:.1f}M",
              delta=f"{soy.components.get('n_invoices')} invoices")
    c3.metric("Avg days to due",
              f"{soy.components.get('avg_days_to_due')}")


def _step4(cur) -> None:
    st.markdown("---")
    st.subheader("4 · OTS components for Big Bird")
    provenance_badge.render("derived", "OTS · last 90 days")
    ots = REGISTRY["ots"].compute_cached(REPRESENTATIVE, cur)
    st.json(ots.components)
    if ots.computation_id:
        st.markdown("**Lineage decomposition (depth 2)**")
        st.json(api.decompose(ots.computation_id, depth=2))


def _step5(cur) -> None:
    st.markdown("---")
    st.subheader("5 · Source events — actual deliveries (modelled ring)")
    provenance_badge.render("modelled", "delivery events")
    con = get_connection(read_only=True)
    try:
        df = con.execute(
            """
            SELECT delivery_id, delivery_date, ingredient_id,
                   ordered_qty, delivered_qty, quality_pass_qty,
                   delay_days, status
            FROM deliveries
            WHERE supplier_id = ?
              AND delivery_date BETWEEN ? AND ?
            ORDER BY delivery_date DESC LIMIT 50
            """,
            [REPRESENTATIVE,
             (cur - pd.Timedelta(days=90)).date(), cur.date()],
        ).fetchdf()
    finally:
        con.close()
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.caption(
        "These are the terminal nodes — every value above traced back to "
        "individual delivery events. No further decomposition possible."
    )


if __name__ == "__main__":
    main()
