"""User-constructed entity runtime (SPEC.md 3.6, CLAUDE.md 5)."""
from __future__ import annotations

from datetime import datetime

import duckdb

from derived.base import ComputationResult


def compute(entity_id: str, at_time: datetime, db: duckdb.DuckDBPyConnection) -> ComputationResult:
    raise NotImplementedError
