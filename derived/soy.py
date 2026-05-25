"""SOY — Supplier Originatable Yield. See SPEC §4.3 / CLAUDE.md §4."""
from __future__ import annotations

from datetime import datetime

from backend.db import get_connection
from derived.base import ComputationResult, Entity, InputRef
from derived.ots import OTS

DEFAULT_DISCOUNT_RATE = 0.014       # per cycle
DEFAULT_ADVANCE_LEAD_DAYS = 5
RISK_ADJUSTMENT_FACTOR = 0.5        # CLAUDE.md §4 corrected formula


class SOY(Entity):
    ENTITY_TYPE = "soy"
    FORMULA_NAME = "supplier_originatable_yield"
    FORMULA_VERSION = "v1.0.0"

    @classmethod
    def list_targets(cls) -> list[str]:
        return OTS.list_targets()

    @classmethod
    def compute(cls, supplier_id: str, at_time: datetime,
                discount_rate: float = DEFAULT_DISCOUNT_RATE,
                advance_lead_days: int = DEFAULT_ADVANCE_LEAD_DAYS) -> ComputationResult:
        at_date = at_time.date()
        con = get_connection(read_only=True)
        try:
            df = con.execute(
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
                [at_date, at_date, supplier_id, at_date],
            ).fetchdf()
        finally:
            con.close()

        if df.empty:
            return ComputationResult(
                value=0.0,
                components={"outstanding_amount": 0.0, "n_invoices": 0,
                            "avg_days_to_due": 0,
                            "gross_annualised_yield_pct": 0.0,
                            "risk_adjusted_yield_pct": 0.0,
                            "ots_used": None},
                inputs={
                    "outstanding_invoices": InputRef(
                        0, "invoices",
                        {"supplier_id": supplier_id, "unpaid_as_of": str(at_date)},
                        0),
                },
            )

        outstanding = float(df["amount_pkr"].sum())
        avg_days = float(df["days_to_due"].mean())

        # OTS-based risk adjustment.
        ots_result = OTS.compute_cached(supplier_id, at_time)
        ots_value = ots_result.value if isinstance(ots_result.value, (int, float)) else 0.80
        risk_factor = 1.0 - ((1.0 - ots_value) * RISK_ADJUSTMENT_FACTOR)

        total_annualised = 0.0
        for _, inv in df.iterrows():
            duration = max(1.0, float(inv["days_to_due"]) - advance_lead_days)
            cycle_yield = discount_rate * float(inv["amount_pkr"])
            annualised = cycle_yield * (365.0 / duration)
            total_annualised += annualised
        risk_adjusted = total_annualised * risk_factor

        gross_pct = 100.0 * total_annualised / outstanding if outstanding else 0.0
        risk_pct = 100.0 * risk_adjusted / outstanding if outstanding else 0.0

        return ComputationResult(
            value=round(risk_adjusted, 2),
            components={
                "outstanding_amount": round(outstanding, 2),
                "n_invoices": int(len(df)),
                "avg_days_to_due": round(avg_days, 1),
                "gross_annualised_yield_pct": round(gross_pct, 3),
                "risk_adjusted_yield_pct": round(risk_pct, 3),
                "risk_factor": round(risk_factor, 4),
                "ots_used": ots_value,
                "discount_rate": discount_rate,
                "advance_lead_days": advance_lead_days,
            },
            inputs={
                "outstanding_invoices": InputRef(
                    outstanding, "invoices",
                    {"supplier_id": supplier_id, "unpaid_as_of": str(at_date)},
                    int(len(df))),
                "ots_child": InputRef(
                    ots_result.computation_id or "", "computations",
                    {"kind": "child_computation", "entity_type": "ots",
                     "entity_id": supplier_id, "at_time": str(at_time)},
                    1),
            },
        )
