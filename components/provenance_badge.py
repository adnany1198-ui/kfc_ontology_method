"""Coloured provenance badge for tables and individual values."""
from __future__ import annotations

import streamlit as st

_COLOURS = {
    "observed": ":green[OBSERVED]",
    "derived": ":orange[DERIVED]",
    "modelled": ":red[MODELLED]",
}


def badge(provenance: str) -> str:
    return _COLOURS.get(provenance, f":gray[{provenance.upper()}]")


def render(provenance: str, label: str = "") -> None:
    suffix = f" · {label}" if label else ""
    st.markdown(f"**{badge(provenance)}**{suffix}")
