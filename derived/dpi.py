"""DPI — Demand Predictability Index. See SPEC §4.5."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from backend.db import get_connection
from derived.base import ComputationResult, Entity, InputRef


class DPI(Entity):
    ENTITY_TYPE = "dpi"
    FORMULA_NAME = "demand_predictability_index"
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
        at_date = at_time.date()
        window_start = (at_time - timedelta(days=365)).date()
        con = get_connection(read_only=True)
        try:
            df = con.execute(
                """
                SELECT po_date, SUM(line_total_pkr) AS daily_amount
                FROM purchase_orders
                WHERE supplier_id = ?
                  AND po_date BETWEEN ? AND ?
                GROUP BY po_date
                ORDER BY po_date
                """,
                [supplier_id, window_start, at_date],
            ).fetchdf()
        finally:
            con.close()

        if len(df) < 30:
            return ComputationResult(
                value={"insufficient_data": True},
                components={"n_po_days": int(len(df)),
                            "forecast_method": "sma_30"},
                inputs={
                    "po_history": InputRef(
                        int(len(df)), "purchase_orders",
                        {"supplier_id": supplier_id,
                         "po_date_between": [str(window_start), str(at_date)]},
                        int(len(df))),
                },
            )

        idx = pd.date_range(window_start, at_date, freq="D")
        series = df.set_index("po_date")["daily_amount"].reindex(idx, fill_value=0.0)

        accuracies = {}
        for horizon in (30, 60, 90):
            actuals, forecasts = [], []
            for t in range(30, len(series) - horizon):
                forecast = series.iloc[t - 30:t].mean() * horizon
                actual = series.iloc[t:t + horizon].sum()
                if actual <= 0:
                    continue
                forecasts.append(forecast)
                actuals.append(actual)
            if not actuals:
                accuracies[horizon] = 0.0
                continue
            f = pd.Series(forecasts).astype(float)
            a = pd.Series(actuals).astype(float)
            err = (f - a).abs() / a
            accuracies[horizon] = max(0.0, 1.0 - float(err.mean()))

        dpi_score = (
            0.50 * accuracies[30] + 0.30 * accuracies[60] + 0.20 * accuracies[90]
        )

        return ComputationResult(
            value=round(dpi_score, 4),
            components={
                "dpi_30": round(accuracies[30], 4),
                "dpi_60": round(accuracies[60], 4),
                "dpi_90": round(accuracies[90], 4),
                "forecast_method": "sma_30",
                "n_po_days": int(len(df)),
                "history_window_days": int(len(series)),
            },
            inputs={
                "po_history": InputRef(
                    int(len(df)), "purchase_orders",
                    {"supplier_id": supplier_id,
                     "po_date_between": [str(window_start), str(at_date)]},
                    int(len(df))),
            },
        )
