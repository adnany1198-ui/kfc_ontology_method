"""Time cursor state. See SPEC.md Section 3.4 and CLAUDE.md Section 2."""
from __future__ import annotations

from datetime import date, datetime, time
from functools import lru_cache

import streamlit as st

from backend.db import get_connection

CURSOR_KEY = "kfc_ontology_cursor"


@lru_cache(maxsize=1)
def bounds() -> tuple[datetime, datetime]:
    """Intersection of observed and modelled time spans.

    Real POS sets the lower edge; modelled invoices/payments may extend
    past max(POS), in which case events forward of the default cursor are
    visible (with a 'projected' badge) only when the user scrubs forward.
    """
    con = get_connection(read_only=True)
    try:
        pos_min, pos_max = con.execute(
            "SELECT MIN(transaction_timestamp), MAX(transaction_timestamp) "
            "FROM pos_transactions"
        ).fetchone()
        mod_max_pay = con.execute(
            "SELECT MAX(payment_date) FROM payments"
        ).fetchone()[0]
        mod_max_inv = con.execute(
            "SELECT MAX(due_date) FROM invoices"
        ).fetchone()[0]
    finally:
        con.close()
    lo = pos_min or datetime(2026, 1, 1)
    hi = max(filter(None, [pos_max, _as_datetime(mod_max_pay),
                           _as_datetime(mod_max_inv)]))
    return lo, hi


def _as_datetime(d) -> datetime | None:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d
    if isinstance(d, date):
        return datetime.combine(d, time(23, 59, 59))
    return None


def default() -> datetime:
    """Latest observed POS event_time — the 'now' of the dataset."""
    con = get_connection(read_only=True)
    try:
        row = con.execute(
            "SELECT MAX(transaction_timestamp) FROM pos_transactions"
        ).fetchone()
    finally:
        con.close()
    return row[0] or datetime(2026, 5, 25, 23, 59, 59)


def get() -> datetime:
    return st.session_state.get(CURSOR_KEY) or default()


def set(at_time: datetime) -> None:  # noqa: A001 — mirrors API
    st.session_state[CURSOR_KEY] = at_time
