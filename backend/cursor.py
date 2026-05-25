"""Time cursor state. See SPEC.md Section 3.4 and CLAUDE.md Section 2."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

CURSOR_KEY = "kfc_ontology_cursor"


def get() -> datetime:
    raise NotImplementedError


def set(at_time: datetime) -> None:
    raise NotImplementedError


def default() -> datetime:
    raise NotImplementedError


def bounds() -> tuple[datetime, datetime]:
    raise NotImplementedError
