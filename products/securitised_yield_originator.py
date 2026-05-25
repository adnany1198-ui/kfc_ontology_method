"""Securitised Yield Originator. See SPEC §5.4."""
from __future__ import annotations

from datetime import datetime

from derived.ccc import CCC
from derived.soy import SOY
from products.base import ProductSimulation, SETTLEMENT_RAILS

PRODUCT_ID = "securitised_yield_originator"
NAME = "Securitised Yield Originator"
SCORE_INPUT = "ots"
DEFAULT_PARAMETERS = {
    "score_threshold": 0.78,
    "pool_target_size_pkr": 500_000_000,
    "origination_fee_bps": 50,
    "target_investor_yield_pct": 12.0,
    "concentration_limit_pct": 25.0,
    "settlement_rail": "bank",
    "score_entity": "ots",
}


def simulate(parameters: dict, at_time: datetime) -> ProductSimulation:
    p = {**DEFAULT_PARAMETERS, **(parameters or {})}
    threshold = float(p["score_threshold"])
    pool_target = float(p["pool_target_size_pkr"])
    fee_bps = float(p["origination_fee_bps"])
    investor_yield_pct = float(p["target_investor_yield_pct"])
    conc_limit_pct = float(p["concentration_limit_pct"])
    rail = p["settlement_rail"]
    score_entity = p.get("score_entity", "ots")

    # Compute SOY for every supplier with a sufficient score.
    candidates = []
    parameter_traces = {"score_entity": score_entity, "scores": {}, "rail": rail}
    for sup in SOY.list_targets():
        score_r = _score_for(score_entity, sup, at_time)
        score_value = score_r.value if isinstance(score_r.value, (int, float)) else None
        parameter_traces["scores"][sup] = {
            "value": score_value, "computation_id": score_r.computation_id,
        }
        if score_value is None or score_value < threshold:
            continue
        soy_r = SOY.compute_cached(sup, at_time)
        if not isinstance(soy_r.value, (int, float)) or soy_r.value <= 0:
            continue
        outstanding = float(soy_r.components.get("outstanding_amount", 0.0))
        if outstanding <= 0:
            continue
        candidates.append({
            "supplier_id": sup,
            "score": score_value,
            "soy_annualised": float(soy_r.value),
            "outstanding": outstanding,
            "yield_rate": float(soy_r.value) / outstanding,
            "soy_computation_id": soy_r.computation_id,
        })

    # Rank by yield rate (efficient frontier), build pool respecting concentration.
    candidates.sort(key=lambda x: -x["yield_rate"])
    conc_cap_pkr = pool_target * conc_limit_pct / 100.0
    pool = []
    pool_size = 0.0
    pool_gross_yield = 0.0
    excluded = []
    for c in candidates:
        size = min(c["outstanding"], conc_cap_pkr, pool_target - pool_size)
        if size <= 0:
            excluded.append({**c, "reason": "pool filled"})
            continue
        contribution = c["soy_annualised"] * (size / c["outstanding"])
        pool.append({**c, "pool_size_pkr": size, "yield_contribution_pkr": contribution})
        pool_size += size
        pool_gross_yield += contribution
        if pool_size >= pool_target * 0.999:
            break

    origination_fee = pool_size * fee_bps / 10000.0
    investor_yield_paid = pool_size * investor_yield_pct / 100.0
    retained_spread = pool_gross_yield - investor_yield_paid

    # Settlement rail impact via CCC.
    ccc_at_rail = CCC.compute("system", at_time, rail=rail).value
    ccc_bank = CCC.compute("system", at_time, rail="bank").value
    days_saved = float(ccc_bank) - float(ccc_at_rail)
    daily_pool_yield = pool_gross_yield / 365.0
    settlement_value = daily_pool_yield * days_saved

    eligible_targets = (
        [{"target_id": c["supplier_id"], "included": True,
          "reason": f"yield_rate {c['yield_rate']*100:.2f}%"} for c in pool] +
        [{"target_id": c["supplier_id"], "included": False,
          "reason": c.get("reason", "below threshold")} for c in excluded]
    )

    aggregate = {
        "pool_size_pkr": round(pool_size, 2),
        "n_suppliers_included": len(pool),
        "pool_gross_yield_pkr": round(pool_gross_yield, 2),
        "origination_fee_pkr": round(origination_fee, 2),
        "investor_yield_paid_pkr": round(investor_yield_paid, 2),
        "retained_spread_pkr": round(retained_spread, 2),
        "originator_revenue_pkr": round(origination_fee + retained_spread, 2),
        "ccc_days_at_rail": ccc_at_rail,
        "ccc_days_bank_baseline": ccc_bank,
        "settlement_rail_value_pkr": round(settlement_value, 2),
        "rail": rail,
    }

    per_target = [{
        "target_id": c["supplier_id"],
        "score_values": {score_entity: c["score"]},
        "contribution_amount": round(c["yield_contribution_pkr"], 2),
        "rate_applied": c["yield_rate"],
        "pool_size_pkr": round(c["pool_size_pkr"], 2),
    } for c in pool]

    return ProductSimulation(
        eligible_targets=eligible_targets,
        aggregate_metrics=aggregate,
        per_target_outcomes=per_target,
        parameter_traces=parameter_traces,
    )


def _score_for(score_entity: str, target_id: str, at_time: datetime):
    if score_entity.startswith("user:"):
        from derived import user_entities
        return user_entities.compute(score_entity[len("user:"):], target_id, at_time)
    from derived import REGISTRY
    return REGISTRY[score_entity].compute_cached(target_id, at_time)
