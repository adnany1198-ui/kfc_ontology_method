"""Sidebar date slider for the time cursor."""
from __future__ import annotations

from datetime import date, datetime, time

import streamlit as st

from backend import cursor


def render() -> datetime:
    lo, hi = cursor.bounds()
    default = cursor.default()
    cur = cursor.get()

    st.sidebar.markdown("### Time cursor")
    picked = st.sidebar.slider(
        "at_time",
        min_value=lo.date(),
        max_value=hi.date(),
        value=cur.date(),
        step=None,
        format="YYYY-MM-DD",
        label_visibility="collapsed",
    )
    chosen = datetime.combine(picked, time(23, 59, 59))
    cursor.set(chosen)

    projected = chosen > default
    badge = ":violet[projected]" if projected else ":green[observed]"
    st.sidebar.markdown(
        f"**{chosen.date()}** &nbsp;·&nbsp; {badge}",
    )
    if projected:
        st.sidebar.caption(
            "forward of latest observed POS event — modelled flows only"
        )
    elif chosen.date() < default.date():
        st.sidebar.caption(f"latest observed: {default.date()}")
    return chosen
