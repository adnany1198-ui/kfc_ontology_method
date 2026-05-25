"""Data Layer page — three columns (observed/derived/modelled)."""
from __future__ import annotations

import streamlit as st

from backend import api
from backend.db import get_connection
from components import provenance_badge, time_cursor_widget


def main() -> None:
    st.set_page_config(page_title="Data Layer", layout="wide")
    cur = time_cursor_widget.render()

    st.title("Data Layer")
    st.caption(
        "Three rings of provenance, temporally aligned at "
        f"**{cur.date()}**. Every value below filters on the cursor."
    )

    observed, derived, modelled = st.columns(3)

    with observed:
        provenance_badge.render("observed", "Real POS")
        _observed_panel(cur)
    with derived:
        provenance_badge.render("derived", "POS × recipes")
        _derived_panel(cur)
    with modelled:
        provenance_badge.render("modelled", "Synthetic supply chain")
        _modelled_panel(cur)


def _observed_panel(cur) -> None:
    con = get_connection(read_only=True)
    try:
        today = con.execute(
            "SELECT COUNT(*) tx, COALESCE(SUM(basket_value), 0) rev, "
            "       COUNT(DISTINCT store_id) stores "
            "FROM pos_transactions "
            "WHERE CAST(transaction_timestamp AS DATE) = ?",
            [cur.date()],
        ).fetchone()
        st.metric("Transactions today", f"{today[0]:,}",
                  delta=f"{today[2]} stores trading")
        st.metric("Revenue today", f"PKR {today[1]/1e6:.2f}M")

        st.markdown("**Top 5 stores by revenue today**")
        st.dataframe(
            con.execute(
                "SELECT store_id, COUNT(*) tx, "
                "       SUM(basket_value) revenue_pkr "
                "FROM pos_transactions "
                "WHERE CAST(transaction_timestamp AS DATE) = ? "
                "GROUP BY store_id "
                "ORDER BY revenue_pkr DESC LIMIT 5",
                [cur.date()],
            ).fetchdf(),
            hide_index=True,
        )

        st.markdown("**Channel mix today**")
        st.dataframe(
            con.execute(
                """
                SELECT COALESCE(channel, 'unknown') AS channel,
                       COUNT(DISTINCT li.transaction_id) AS tx,
                       SUM(li.line_total) AS revenue_pkr
                FROM pos_line_items li
                WHERE CAST(li.transaction_timestamp AS DATE) = ?
                GROUP BY channel ORDER BY revenue_pkr DESC
                """,
                [cur.date()],
            ).fetchdf(),
            hide_index=True,
        )

        st.markdown("**Top 10 SKUs today (by revenue)**")
        st.dataframe(
            con.execute(
                """
                SELECT product_id, base_name,
                       SUM(quantity) units,
                       SUM(line_total) revenue_pkr
                FROM pos_line_items
                WHERE CAST(transaction_timestamp AS DATE) = ?
                GROUP BY product_id, base_name
                ORDER BY revenue_pkr DESC LIMIT 10
                """,
                [cur.date()],
            ).fetchdf(),
            hide_index=True,
        )
    finally:
        con.close()


def _derived_panel(cur) -> None:
    con = get_connection(read_only=True)
    try:
        agg = con.execute(
            "SELECT COUNT(DISTINCT ingredient_id) n_ing, "
            "       SUM(consumed_qty) total "
            "FROM ingredient_consumption_daily WHERE date = ?",
            [cur.date()],
        ).fetchone()
        st.metric("Ingredients consumed today", f"{agg[0] or 0}")
        st.metric("Recipe-mapping revenue coverage",
                  f"{_recipe_coverage(con)*100:.2f}%")

        st.markdown("**Top ingredients consumed today**")
        st.dataframe(
            con.execute(
                """
                SELECT i.name, c.consumed_qty, c.unit
                FROM ingredient_consumption_daily c
                JOIN ingredients i ON i.ingredient_id = c.ingredient_id
                WHERE c.date = ?
                ORDER BY c.consumed_qty DESC LIMIT 10
                """,
                [cur.date()],
            ).fetchdf(),
            hide_index=True,
        )

        st.markdown("**Per-store approx COGS today (top 5)**")
        st.dataframe(
            con.execute(
                """
                SELECT c.store_id,
                       COUNT(DISTINCT c.ingredient_id) n_ing,
                       SUM(c.consumed_qty * COALESCE(i.current_price_pkr_unit, 0))
                         AS approx_cogs_pkr
                FROM ingredient_consumption_daily c
                JOIN ingredients i ON i.ingredient_id = c.ingredient_id
                WHERE c.date = ?
                GROUP BY c.store_id
                ORDER BY approx_cogs_pkr DESC LIMIT 5
                """,
                [cur.date()],
            ).fetchdf(),
            hide_index=True,
        )
    finally:
        con.close()


def _modelled_panel(cur) -> None:
    con = get_connection(read_only=True)
    try:
        poss = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(line_total_pkr), 0) "
            "FROM purchase_orders WHERE po_date = ?",
            [cur.date()],
        ).fetchone()
        dels = con.execute(
            "SELECT COUNT(*) FROM deliveries WHERE delivery_date = ?",
            [cur.date()],
        ).fetchone()
        out = api.get_data_layer_summary(cur)
        st.metric("POs issued today", f"{poss[0]} · PKR {poss[1]/1e6:.2f}M")
        st.metric("Deliveries received today", f"{dels[0]}")
        st.metric("Outstanding AP", f"PKR {out['modelled_ap_outstanding']/1e6:.1f}M")
        st.metric("Due next 7d", f"PKR {out['modelled_pay_next_7']/1e6:.1f}M")

        st.markdown("**POs issued today (top 5)**")
        st.dataframe(
            con.execute(
                """
                SELECT po_id, supplier_id, ingredient_id,
                       order_qty, line_total_pkr
                FROM purchase_orders WHERE po_date = ?
                ORDER BY line_total_pkr DESC LIMIT 5
                """,
                [cur.date()],
            ).fetchdf(),
            hide_index=True,
        )

        st.markdown("**Invoices outstanding (top 10)**")
        st.dataframe(
            con.execute(
                """
                SELECT i.invoice_id, i.supplier_id, i.amount_pkr,
                       i.due_date,
                       DATE_DIFF('day', ?, i.due_date) AS days_to_due
                FROM invoices i
                LEFT JOIN payments p ON p.invoice_id = i.invoice_id
                                    AND p.payment_date <= ?
                WHERE i.invoice_date <= ? AND p.payment_id IS NULL
                ORDER BY i.amount_pkr DESC LIMIT 10
                """,
                [cur.date(), cur.date(), cur.date()],
            ).fetchdf(),
            hide_index=True,
        )
    finally:
        con.close()


def _recipe_coverage(con) -> float:
    row = con.execute(
        """
        SELECT SUM(CASE WHEN m.real_sku_id IS NOT NULL THEN li.line_total ELSE 0 END),
               SUM(li.line_total)
        FROM pos_line_items li
        LEFT JOIN (SELECT DISTINCT real_sku_id FROM sku_recipe_mapping) m
          ON m.real_sku_id = li.product_id
        """
    ).fetchone()
    return float(row[0] or 0) / float(row[1] or 1)


if __name__ == "__main__":
    main()
