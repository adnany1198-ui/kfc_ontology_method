"""Captive Invoice Financing (SPEC.md 5.2)."""
from __future__ import annotations

from datetime import datetime

import duckdb

from products.base import ProductSimulation


def simulate(parameters: dict, at_time: datetime, db: duckdb.DuckDBPyConnection) -> ProductSimulation:
    raise NotImplementedError


def default_parameters() -> dict:
    raise NotImplementedError
