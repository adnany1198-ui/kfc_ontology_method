"""Credit Products page — three product tabs. See SPEC §7.4."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from backend import api
from components import provenance_badge, time_cursor_widget
from products import REGISTRY
from products.base import SETTLEMENT_RAILS


def main() -> None:
    st.set_page_config(page_title="Credit Products", layout="wide")
    cur = time_cursor_widget.render()
    st.title("Credit Products")
    provenance_badge.render("derived", f"simulating at cursor {cur.date()}")

    tabs = st.tabs([p.NAME for p in REGISTRY.values()])
    for tab, (pid, product) in zip(tabs, REGISTRY.items()):
        with tab:
            _product_panel(pid, product, cur)


def _product_panel(pid, product, cur) -> None:
    left, center, right = st.columns([1, 2, 1])
    with left:
        st.markdown("### Parameters")
        params = _parameter_inputs(pid, product, cur)
        if st.button("Reset to defaults", key=f"reset_{pid}"):
            st.session_state[f"params_{pid}"] = dict(product.DEFAULT_PARAMETERS)
            st.rerun()

    sim = product.simulate(params, cur)

    with center:
        st.markdown("### Output")
        _output_panel(pid, sim)

    with right:
        st.markdown("### Lineage")
        _lineage_panel(pid, sim, cur)


def _parameter_inputs(pid, product, cur) -> dict:
    state_key = f"params_{pid}"
    if state_key not in st.session_state:
        st.session_state[state_key] = dict(product.DEFAULT_PARAMETERS)
    p = dict(st.session_state[state_key])

    # Score-input selector (built-in entity or user-constructed)
    options = ["ots", "dpi"]
    user_entities = api.list_user_entities()
    options += [f"user:{u['user_entity_id']}" for u in user_entities]
    default_se = p.get("score_entity", product.SCORE_INPUT)
    if default_se not in options:
        options.insert(0, default_se)
    p["score_entity"] = st.selectbox(
        "Score input", options, index=options.index(default_se),
        key=f"se_{pid}",
        help="Built-in entity or user-constructed entity (Compose page).",
    )

    if "score_threshold" in p:
        p["score_threshold"] = st.slider(
            "Score threshold", 0.0, 1.0, float(p["score_threshold"]),
            step=0.01, key=f"st_{pid}",
        )
    if "advance_lead_days" in p:
        p["advance_lead_days"] = st.slider(
            "Advance lead days", 0, 30, int(p["advance_lead_days"]),
            key=f"al_{pid}",
        )
    if "commitment_horizon_days" in p:
        p["commitment_horizon_days"] = st.slider(
            "Commitment horizon (days)", 30, 180,
            int(p["commitment_horizon_days"]), step=15, key=f"ch_{pid}",
        )
    if "advance_ratio" in p:
        p["advance_ratio"] = st.slider(
            "Advance ratio", 0.0, 1.0, float(p["advance_ratio"]),
            step=0.05, key=f"ar_{pid}",
        )
    if "expected_drawdown_rate" in p:
        p["expected_drawdown_rate"] = st.slider(
            "Expected drawdown rate", 0.0, 1.0,
            float(p["expected_drawdown_rate"]), step=0.05, key=f"dr_{pid}",
        )
    if "pool_target_size_pkr" in p:
        p["pool_target_size_pkr"] = st.number_input(
            "Pool target (PKR)", min_value=0,
            value=int(p["pool_target_size_pkr"]),
            step=10_000_000, key=f"ps_{pid}",
        )
    if "origination_fee_bps" in p:
        p["origination_fee_bps"] = st.slider(
            "Origination fee (bps)", 0, 300,
            int(p["origination_fee_bps"]), step=5, key=f"of_{pid}",
        )
    if "target_investor_yield_pct" in p:
        p["target_investor_yield_pct"] = st.slider(
            "Investor yield (%)", 0.0, 30.0,
            float(p["target_investor_yield_pct"]), step=0.5,
            key=f"iy_{pid}",
        )
    if "concentration_limit_pct" in p:
        p["concentration_limit_pct"] = st.slider(
            "Concentration limit (%)", 0.0, 100.0,
            float(p["concentration_limit_pct"]), step=5.0,
            key=f"cl_{pid}",
        )
    if "settlement_rail" in p:
        p["settlement_rail"] = st.radio(
            "Settlement rail", list(SETTLEMENT_RAILS.keys()),
            index=list(SETTLEMENT_RAILS.keys()).index(p["settlement_rail"]),
            horizontal=True, key=f"sr_{pid}",
        )

    st.session_state[state_key] = p
    return p


def _output_panel(pid, sim) -> None:
    cols = st.columns(min(4, len(sim.aggregate_metrics)))
    for i, (k, v) in enumerate(list(sim.aggregate_metrics.items())[:4]):
        with cols[i]:
            if isinstance(v, (int, float)) and abs(v) > 1e6:
                st.metric(k, f"PKR {v/1e6:.1f}M")
            else:
                st.metric(k, _fmt(v))

    st.markdown("**All aggregate metrics**")
    st.json(sim.aggregate_metrics)

    if sim.per_target_outcomes:
        st.markdown("**Per-target outcomes**")
        df = pd.DataFrame(sim.per_target_outcomes)
        st.dataframe(df.sort_values("contribution_amount", ascending=False),
                     hide_index=True, use_container_width=True)

    if pid == "securitised_yield_originator":
        _settlement_rail_widget(sim)

    st.markdown("**Eligibility breakdown**")
    elig_df = pd.DataFrame(sim.eligible_targets)
    st.dataframe(elig_df, hide_index=True, use_container_width=True)


def _settlement_rail_widget(sim) -> None:
    st.markdown("---")
    st.markdown("**Settlement rail comparison**")
    cur = api.get_cursor()
    from derived.ccc import CCC
    from products.securitised_yield_originator import simulate as sim_fn
    rows = []
    base_params = {}  # use defaults but vary rail
    for rail in ["bank", "raast", "stablecoin"]:
        s = sim_fn({**base_params, "settlement_rail": rail}, cur)
        rows.append({
            "rail": rail,
            "ccc_days": s.aggregate_metrics["ccc_days_at_rail"],
            "pool_yield_pkr": s.aggregate_metrics["pool_gross_yield_pkr"],
            "friction_pkr (vs stablecoin)": None,
        })
    base = next(r for r in rows if r["rail"] == "stablecoin")
    for r in rows:
        r["friction_pkr (vs stablecoin)"] = round(
            (base["pool_yield_pkr"] - r["pool_yield_pkr"]) * 0
            + base["ccc_days"] - r["ccc_days"], 2)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _lineage_panel(pid, sim, cur) -> None:
    se = sim.parameter_traces.get("score_entity")
    if se:
        st.caption(f"Score entity used: **{se}**")
    scores = sim.parameter_traces.get("scores", {})
    if scores:
        st.markdown("**Score values consulted**")
        rows = []
        for tid, info in scores.items():
            rows.append({
                "target": tid,
                "value": info.get("value"),
                "tier": info.get("tier"),
                "computation_id": info.get("computation_id"),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     use_container_width=True, height=320)

    eligible = [t for t in sim.per_target_outcomes]
    if eligible:
        picked = st.selectbox(
            "Decompose contribution from", [t["target_id"] for t in eligible],
            key=f"decomp_{pid}",
        )
        score_info = scores.get(picked, {})
        cid = score_info.get("computation_id")
        if cid:
            st.markdown("**Score lineage**")
            st.json(api.decompose(cid, depth=2))


def _fmt(v):
    if isinstance(v, float):
        return f"{v:,.2f}"
    return v


if __name__ == "__main__":
    main()
