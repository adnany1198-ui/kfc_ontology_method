"""Forward / Pre-Invoice Credit. See SPEC §5.3."""
from __future__ import annotations

from datetime import datetime, timedelta

from backend.db import get_connection
from products.base import ProductSimulation

PRODUCT_ID = "forward_credit"
NAME = "Forward / Pre-Invoice Credit"
SCORE_INPUT = "dpi"
DEFAULT_PARAMETERS = {
    # DPI in this dataset runs low (0.23–0.27 for suppliers with enough PO
    # history) because SMA-30 forecasts diverge sharply over 60/90-day
    # horizons. Threshold dropped to 0.20 to keep the simulator usable on
    # the modelled stream; the canonical SPEC default (0.70) returns to
    # service once forecasts improve in v1.5.
    "score_threshold": 0.20,
    "commitment_horizon_days": 90,
    "advance_ratio": 0.40,
    "discount_rate_by_band": {
        "high":   {"min": 0.25, "rate": 0.012},
        "mid":    {"min": 0.22, "rate": 0.016},
        "low":    {"min": 0.20, "rate": 0.020},
    },
    "expected_drawdown_rate": 0.65,
    "max_deployment_pkr": None,
    "score_entity": "dpi",
}


def simulate(parameters: dict, at_time: datetime) -> ProductSimulation:
    p = {**DEFAULT_PARAMETERS, **(parameters or {})}
    threshold = float(p["score_threshold"])
    horizon = int(p["commitment_horizon_days"])
    advance = float(p["advance_ratio"])
    drawdown = float(p["expected_drawdown_rate"])
    score_entity = p.get("score_entity", "dpi")
    bands = p["discount_rate_by_band"]

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
    total_committed = 0.0
    total_yield = 0.0

    for sup in suppliers:
        score_result = _score_for(score_entity, sup, at_time)
        score_value = score_result.value if isinstance(score_result.value, (int, float)) else None
        parameter_traces["scores"][sup] = {
            "value": score_value,
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

        forecast = _forecast_po_volume(sup, at_time, horizon)
        if forecast <= 0:
            eligible_targets.append({"target_id": sup, "included": False,
                                     "reason": "zero forecast"})
            continue

        credit_line = forecast * advance
        rate = _rate_for(score_value, bands)
        drawn = credit_line * drawdown
        annualised_yield = drawn * rate * (365.0 / horizon)

        eligible_targets.append({"target_id": sup, "included": True,
                                 "reason": f"DPI {score_value:.3f}, rate {rate*100:.2f}%"})
        per_target.append({
            "target_id": sup,
            "score_values": {score_entity: score_value},
            "forecast_po_pkr": round(forecast, 2),
            "credit_line_pkr": round(credit_line, 2),
            "expected_drawn_pkr": round(drawn, 2),
            "rate_applied": rate,
            "contribution_amount": round(annualised_yield, 2),
        })
        total_committed += credit_line
        total_yield += annualised_yield

    aggregate = {
        "n_eligible": sum(1 for e in eligible_targets if e["included"]),
        "n_excluded": sum(1 for e in eligible_targets if not e["included"]),
        "total_credit_committed_pkr": round(total_committed, 2),
        "expected_drawdown_rate": drawdown,
        "total_deployment_pkr": round(total_committed * drawdown, 2),
        "total_yield_annualised_pkr": round(total_yield, 2),
        "commitment_horizon_days": horizon,
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


def _forecast_po_volume(supplier_id: str, at_time: datetime,
                        horizon_days: int) -> float:
    """SMA over the last 30 PO days × horizon — same as DPI's forecaster."""
    window_start = (at_time - timedelta(days=30)).date()
    con = get_connection(read_only=True)
    try:
        row = con.execute(
            """
            SELECT COALESCE(AVG(daily_total), 0)
            FROM (
              SELECT po_date, SUM(line_total_pkr) AS daily_total
              FROM purchase_orders
              WHERE supplier_id = ? AND po_date BETWEEN ? AND ?
              GROUP BY po_date
            )
            """,
            [supplier_id, window_start, at_time.date()],
        ).fetchone()
    finally:
        con.close()
    return float(row[0] or 0.0) * horizon_days


def _rate_for(score: float, bands: dict) -> float:
    if score >= bands["high"]["min"]:
        return float(bands["high"]["rate"])
    if score >= bands["mid"]["min"]:
        return float(bands["mid"]["rate"])
    return float(bands["low"]["rate"])
