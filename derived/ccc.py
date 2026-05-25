"""CCC — Cash Conversion Coefficient (SPEC.md 4.4, settlement rails per CLAUDE.md 4)."""
from __future__ import annotations

from datetime import datetime

import duckdb

from derived.base import ComputationResult


def compute(entity_id: str, at_time: datetime, db: duckdb.DuckDBPyConnection) -> ComputationResult:
    raise NotImplementedError
