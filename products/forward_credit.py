"""Forward / Pre-Invoice Credit (SPEC.md 5.3)."""
from __future__ import annotations

from datetime import datetime

import duckdb

from products.base import ProductSimulation


def simulate(parameters: dict, at_time: datetime, db: duckdb.DuckDBPyConnection) -> ProductSimulation:
    raise NotImplementedError


def default_parameters() -> dict:
    raise NotImplementedError
