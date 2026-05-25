"""Shared types for derived entities. See CLAUDE.md Section 3."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass
class InputRef:
    value: Union[float, int, str, dict]
    source_table: str
    source_filter: str
    source_row_count: int


@dataclass
class ComputationResult:
    value: Union[float, dict]
    components: dict[str, float]
    inputs: dict[str, InputRef]
    formula_version: str
