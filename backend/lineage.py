"""Lineage persistence and decomposition. See SPEC.md Section 3.5, CLAUDE.md Section 3."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from derived.base import ComputationResult


def persist(
    entity_type: str,
    entity_id: str,
    at_time: datetime,
    result: ComputationResult,
) -> str:
    raise NotImplementedError


def lookup(
    entity_type: str,
    entity_id: str,
    at_time: datetime,
    formula_version: str,
) -> str | None:
    raise NotImplementedError


def decompose(computation_id: str, depth: int = 1) -> dict:
    raise NotImplementedError
