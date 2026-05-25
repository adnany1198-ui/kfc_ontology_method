"""CCC — Cash Conversion Coefficient. See SPEC §4.4 / CLAUDE.md §4."""
from __future__ import annotations

from datetime import datetime, timedelta

from backend.db import get_connection
from derived.base import ComputationResult, Entity, InputRef

SETTLEMENT_RAILS = {
    "bank":       {"settlement_latency": 3, "processing_overhead": 2},
    "raast":      {"settlement_latency": 0, "processing_overhead": 1},
    "stablecoin": {"settlement_latency": 0, "processing_overhead": 0},
}

INDUSTRY_DEFAULT_COGS_RATIO = 0.42


class CCC(Entity):
    ENTITY_TYPE = "ccc"
    FORMULA_NAME = "cash_conversion_coefficient"
    FORMULA_VERSION = "v1.0.0"

    @classmethod
    def list_targets(cls) -> list[str]:
        return ["system"]

    @classmethod
    def compute(cls, entity_id: str, at_time: datetime,
                rail: str = "bank") -> ComputationResult:
        at_date = at_time.date()
        window_start = (at_time - timedelta(days=30)).date()
        rail_params = SETTLEMENT_RAILS.get(rail, SETTLEMENT_RAILS["bank"])

        con = get_connection(read_only=True)
        try:
            pos_rev = float(con.execute(
                """
                SELECT COALESCE(SUM(basket_value), 0)
                FROM pos_transactions
                WHERE transaction_timestamp BETWEEN ? AND ?
                """,
                [datetime.combine(window_start, datetime.min.time()), at_time],
            ).fetchone()[0])

            cogs_row = con.execute(
                """
                SELECT COALESCE(SUM(c.consumed_qty * i.current_price_pkr_unit), 0),
                       COUNT(DISTINCT c.date)
                FROM ingredient_consumption_daily c
                JOIN ingredients i ON i.ingredient_id = c.ingredient_id
                WHERE c.date BETWEEN ? AND ?
                """,
                [window_start, at_date],
            ).fetchone()
            cogs_derived = float(cogs_row[0])
            n_cogs_days = int(cogs_row[1] or 0)

            # COGS-weighted payment terms across suppliers (weighting by
            # paid-or-invoiced amount as the COGS proxy per CLAUDE.md §4).
            terms_row = con.execute(
                """
                WITH supplier_cogs AS (
                  SELECT s.supplier_id, s.payment_terms_days,
                         COALESCE(SUM(i.amount_pkr), 0) AS exposure
                  FROM suppliers s
                  LEFT JOIN invoices i ON i.supplier_id = s.supplier_id
                                       AND i.invoice_date <= ?
                  GROUP BY s.supplier_id, s.payment_terms_days
                )
                SELECT
                  SUM(payment_terms_days * exposure)::DOUBLE
                    / NULLIF(SUM(exposure), 0) AS weighted_avg
                FROM supplier_cogs
                WHERE exposure > 0
                """,
                [at_date],
            ).fetchone()
            payment_terms_weighted_avg = float(terms_row[0] or 30.0)

            # Recipe coverage — fall back to industry COGS ratio when low.
            cov_row = con.execute(
                """
                SELECT SUM(CASE WHEN m.real_sku_id IS NOT NULL
                                THEN li.line_total ELSE 0 END),
                       SUM(li.line_total)
                FROM pos_line_items li
                LEFT JOIN (SELECT DISTINCT real_sku_id FROM sku_recipe_mapping) m
                  ON m.real_sku_id = li.product_id
                WHERE li.transaction_timestamp BETWEEN ? AND ?
                """,
                [datetime.combine(window_start, datetime.min.time()), at_time],
            ).fetchone()
            mapped_rev = float(cov_row[0] or 0)
            total_rev = float(cov_row[1] or 0)
            recipe_coverage = (mapped_rev / total_rev) if total_rev else 0.0
        finally:
            con.close()

        used_fallback = recipe_coverage < 0.75
        if used_fallback:
            cogs_pkr = pos_rev * INDUSTRY_DEFAULT_COGS_RATIO
            cogs_source = "industry_default_42pct"
        else:
            cogs_pkr = cogs_derived
            cogs_source = "derived_consumption_x_price"

        days = max(n_cogs_days, 1)
        daily_cogs = cogs_pkr / days if days else 0.0
        effective_cycle = (
            payment_terms_weighted_avg
            + rail_params["settlement_latency"]
            + rail_params["processing_overhead"]
        )
        deployable_float = daily_cogs * effective_cycle

        return ComputationResult(
            value=round(effective_cycle, 2),
            components={
                "payment_terms_weighted_avg": round(payment_terms_weighted_avg, 2),
                "settlement_latency": rail_params["settlement_latency"],
                "processing_overhead": rail_params["processing_overhead"],
                "rail": rail,
                "daily_cogs_pkr": round(daily_cogs, 2),
                "deployable_float_pkr": round(deployable_float, 2),
                "cogs_source": cogs_source,
                "recipe_coverage": round(recipe_coverage, 4),
                "pos_revenue_window_pkr": round(pos_rev, 2),
                "n_cogs_days": n_cogs_days,
            },
            inputs={
                "pos_revenue_30d": InputRef(
                    pos_rev, "pos_transactions",
                    {"transaction_timestamp_between":
                     [str(window_start), str(at_time)]},
                    1),
                "cogs_30d": InputRef(
                    cogs_pkr, "ingredient_consumption_daily" if not used_fallback
                                 else "industry_default",
                    {"date_between": [str(window_start), str(at_date)]},
                    n_cogs_days),
                "supplier_payment_terms": InputRef(
                    payment_terms_weighted_avg, "suppliers",
                    {"weighting": "invoice_amount_to_date"}, 0),
            },
        )
