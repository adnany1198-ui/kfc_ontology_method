"""Captive Invoice Financing. See SPEC §5.2."""
from __future__ import annotations

from datetime import datetime

from backend.db import get_connection
from derived.ots import OTS
from products.base import ProductSimulation

PRODUCT_ID = "captive_invoice_financing"
NAME = "Captive Invoice Financing"
SCORE_INPUT = "ots"
DEFAULT_PARAMETERS = {
    "score_threshold": 0.78,
    "discount_rate_by_tier": {"A": 0.009, "B": 0.013, "C": 0.017},
    "advance_lead_days": 5,
    "max_deployment_pkr": None,
    "score_entity": "ots",
}


def simulate(parameters: dict, at_time: datetime) -> ProductSimulation:
    p = {**DEFAULT_PARAMETERS, **(parameters or {})}
    threshold = float(p["score_threshold"])
    discount_by_tier = p["discount_rate_by_tier"]
    advance_lead = int(p["advance_lead_days"])
    max_deploy = p["max_deployment_pkr"]
    score_entity = p.get("score_entity", "ots")

    con = get_connection(read_only=True)
    try:
        suppliers = [r[0] for r in con.execute(
            "SELECT supplier_id FROM suppliers ORDER BY supplier_id"
        ).fetchall()]
    finally:
        con.close()

    eligible_targets = []
    per_target = []
    parameter_traces = {"score_entity": score_entity, "scores": {}}
    deployed_so_far = 0.0
    total_yield = 0.0
    total_outstanding = 0.0
    avg_duration_acc = 0.0
    avg_duration_n = 0

    for sup in suppliers:
        score_result = _score_for(score_entity, sup, at_time)
        score_value = score_result.value if isinstance(score_result.value, (int, float)) else None
        tier = score_result.components.get("tier") if score_result.components else None
        parameter_traces["scores"][sup] = {
            "value": score_value, "tier": tier,
            "computation_id": score_result.computation_id,
        }

        if score_value is None:
            eligible_targets.append({"target_id": sup, "included": False,
                                     "reason": "no score data"})
            continue
        if score_value < threshold:
            eligible_targets.append({"target_id": sup, "included": False,
                                     "reason": f"score {score_value:.3f} < threshold {threshold}"})
            continue

        invs = _outstanding_invoices(sup, at_time)
        if invs.empty:
            eligible_targets.append({"target_id": sup, "included": False,
                                     "reason": "no outstanding invoices"})
            continue

        rate = float(discount_by_tier.get(tier, 0.0)) if tier else 0.0
        if rate <= 0:
            eligible_targets.append({"target_id": sup, "included": False,
                                     "reason": f"tier {tier} blocked"})
            continue

        out_amt = float(invs["amount_pkr"].sum())
        if max_deploy is not None and deployed_so_far + out_amt > float(max_deploy):
            eligible_targets.append({"target_id": sup, "included": False,
                                     "reason": "deployment cap reached"})
            continue

        yld = 0.0
        durations = []
        for _, inv in invs.iterrows():
            d = max(1.0, float(inv["days_to_due"]) - advance_lead)
            durations.append(d)
            yld += rate * float(inv["amount_pkr"]) * (365.0 / d)
        avg_dur = sum(durations) / len(durations) if durations else advance_lead

        eligible_targets.append({"target_id": sup, "included": True,
                                 "reason": f"tier {tier}, rate {rate*100:.2f}%"})
        per_target.append({
            "target_id": sup,
            "score_values": {score_entity: score_value, "tier": tier},
            "contribution_amount": round(yld, 2),
            "rate_applied": rate,
            "outstanding_pkr": round(out_amt, 2),
            "n_invoices": int(len(invs)),
            "avg_duration_days": round(avg_dur, 1),
        })
        deployed_so_far += out_amt
        total_yield += yld
        total_outstanding += out_amt
        avg_duration_acc += avg_dur * len(invs)
        avg_duration_n += len(invs)

    weighted_rate = (total_yield / total_outstanding * 100.0) if total_outstanding else 0.0
    avg_dur = (avg_duration_acc / avg_duration_n) if avg_duration_n else 0.0

    aggregate = {
        "n_eligible": sum(1 for e in eligible_targets if e["included"]),
        "n_excluded": sum(1 for e in eligible_targets if not e["included"]),
        "total_outstanding_pkr": round(total_outstanding, 2),
        "total_yield_annualised_pkr": round(total_yield, 2),
        "weighted_avg_rate_pct": round(weighted_rate, 3),
        "avg_duration_days": round(avg_dur, 1),
    }
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


def _outstanding_invoices(supplier_id: str, at_time: datetime):
    con = get_connection(read_only=True)
    try:
        return con.execute(
            """
            SELECT i.invoice_id, i.amount_pkr,
                   DATE_DIFF('day', ?, i.due_date) AS days_to_due
            FROM invoices i
            LEFT JOIN payments p ON p.invoice_id = i.invoice_id
                                AND p.payment_date <= ?
            WHERE i.supplier_id = ?
              AND i.invoice_date <= ?
              AND p.payment_id IS NULL
            """,
            [at_time.date(), at_time.date(), supplier_id, at_time.date()],
        ).fetchdf()
    finally:
        con.close()
