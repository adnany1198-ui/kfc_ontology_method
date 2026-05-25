"""OTS — Operational Trust Score. See SPEC §4.2 / CLAUDE.md §4."""
from __future__ import annotations

from datetime import datetime, timedelta

from backend.db import get_connection
from derived.base import ComputationResult, Entity, InputRef


def _tier(score: float) -> str:
    if score >= 0.92: return "A"
    if score >= 0.85: return "B"
    if score >= 0.78: return "C"
    return "D"


class OTS(Entity):
    ENTITY_TYPE = "ots"
    FORMULA_NAME = "operational_trust_score"
    FORMULA_VERSION = "v1.0.0"

    @classmethod
    def list_targets(cls) -> list[str]:
        con = get_connection(read_only=True)
        try:
            return [r[0] for r in con.execute(
                "SELECT supplier_id FROM suppliers ORDER BY supplier_id"
            ).fetchall()]
        finally:
            con.close()

    @classmethod
    def compute(cls, supplier_id: str, at_time: datetime) -> ComputationResult:
        window_start = (at_time - timedelta(days=90)).date()
        at_date = at_time.date()

        con = get_connection(read_only=True)
        try:
            d = con.execute(
                """
                SELECT
                  COUNT(*) AS n,
                  SUM(CASE WHEN delay_days <= 0 THEN 1 ELSE 0 END) AS on_time,
                  SUM(CASE WHEN delivered_qty >= 0.95 * ordered_qty THEN 1 ELSE 0 END)
                    AS filled,
                  SUM(quality_pass_qty)::DOUBLE / NULLIF(SUM(delivered_qty), 0)
                    AS quality_pass_rate,
                  AVG(delivered_qty) AS mean_qty,
                  STDDEV_POP(delivered_qty) AS std_qty
                FROM deliveries
                WHERE supplier_id = ?
                  AND delivery_date BETWEEN ? AND ?
                """,
                [supplier_id, window_start, at_date],
            ).fetchone()
            n_deliv = d[0] or 0

            # Payment compliance per CLAUDE.md §4: 1 - (late>7d / total)
            p = con.execute(
                """
                SELECT
                  COUNT(*) AS n,
                  SUM(CASE WHEN days_vs_due > 7 THEN 1 ELSE 0 END) AS late_gt_7
                FROM payments
                WHERE supplier_id = ?
                  AND payment_date BETWEEN ? AND ?
                """,
                [supplier_id, window_start, at_date],
            ).fetchone()
            n_pay = p[0] or 0
        finally:
            con.close()

        if n_deliv == 0:
            return ComputationResult(
                value={"insufficient_data": True},
                components={"n_deliveries_90d": 0, "tier": "N/A"},
                inputs={
                    "deliveries_window": InputRef(
                        0, "deliveries",
                        {"supplier_id": supplier_id,
                         "delivery_date_between": [str(window_start), str(at_date)]},
                        0),
                },
            )

        on_time_rate = (d[1] or 0) / n_deliv
        fill_rate = (d[2] or 0) / n_deliv
        quality_pass_rate = float(d[3] or 0.0)
        mean = float(d[4] or 0.0)
        std = float(d[5] or 0.0)
        volume_consistency = 1.0 - (std / mean) if mean > 0 else 0.0
        volume_consistency = max(0.0, min(1.0, volume_consistency))

        payment_compliance = (
            1.0 - ((p[1] or 0) / n_pay) if n_pay else 1.0
        )

        score = (
            0.30 * on_time_rate
            + 0.20 * fill_rate
            + 0.25 * quality_pass_rate
            + 0.15 * volume_consistency
            + 0.10 * payment_compliance
        )
        tier = _tier(score)

        return ComputationResult(
            value=round(score, 4),
            components={
                "on_time_rate": round(on_time_rate, 4),
                "fill_rate": round(fill_rate, 4),
                "quality_pass_rate": round(quality_pass_rate, 4),
                "volume_consistency": round(volume_consistency, 4),
                "payment_compliance": round(payment_compliance, 4),
                "n_deliveries_90d": n_deliv,
                "n_payments_90d": n_pay,
                "tier": tier,
            },
            inputs={
                "deliveries_window": InputRef(
                    n_deliv, "deliveries",
                    {"supplier_id": supplier_id,
                     "delivery_date_between": [str(window_start), str(at_date)]},
                    n_deliv),
                "payments_window": InputRef(
                    n_pay, "payments",
                    {"supplier_id": supplier_id,
                     "payment_date_between": [str(window_start), str(at_date)]},
                    n_pay),
            },
        )
