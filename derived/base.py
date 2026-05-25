"""Common machinery for derived entities. See SPEC §4 / CLAUDE.md §3."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

import pandas as pd

from backend import lineage


@dataclass
class InputRef:
    value: Any
    source_table: str
    source_filter: dict | str
    source_row_count: int

    def to_dict(self) -> dict:
        f = self.source_filter
        if isinstance(f, dict):
            f = json.dumps(f, default=str, sort_keys=True)
        return {
            "input_value": self.value,
            "source_table": self.source_table,
            "source_filter": f,
            "source_row_count": int(self.source_row_count),
        }


@dataclass
class ComputationResult:
    value: float | dict
    components: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, InputRef] = field(default_factory=dict)
    formula_version: str = "v0.0.0"
    entity_type: str = ""
    entity_id: str = ""
    at_time: datetime | None = None
    computation_id: str | None = None
    formula_name: str = ""


class Entity:
    """Base class for derived entities (OTS, SOY, DPI, CCC)."""

    ENTITY_TYPE: ClassVar[str] = ""
    FORMULA_NAME: ClassVar[str] = ""
    FORMULA_VERSION: ClassVar[str] = "v1.0.0"

    @classmethod
    def list_targets(cls) -> list[str]:
        raise NotImplementedError

    @classmethod
    def compute(cls, entity_id: str, at_time: datetime) -> ComputationResult:
        raise NotImplementedError

    @classmethod
    def compute_cached(cls, entity_id: str, at_time: datetime) -> ComputationResult:
        cached = lineage.lookup(cls.ENTITY_TYPE, entity_id, at_time,
                                cls.FORMULA_VERSION)
        if cached is not None:
            return cached
        result = cls.compute(entity_id, at_time)
        result.entity_type = cls.ENTITY_TYPE
        result.entity_id = entity_id
        result.at_time = at_time
        result.formula_name = cls.FORMULA_NAME
        result.formula_version = cls.FORMULA_VERSION
        result.computation_id = lineage.store(result)
        return result

    @classmethod
    def history(cls, entity_id: str, from_time: datetime,
                to_time: datetime, granularity: str = "daily") -> pd.DataFrame:
        rule = {"daily": "D", "weekly": "W", "monthly": "MS"}.get(granularity, "D")
        index = pd.date_range(from_time, to_time, freq=rule).to_list()
        rows = []
        for t in index:
            r = cls.compute_cached(entity_id, t.to_pydatetime())
            rows.append({
                "at_time": t,
                "value": r.value if not isinstance(r.value, dict) else None,
                **{f"c_{k}": v for k, v in r.components.items()
                   if isinstance(v, (int, float))},
            })
        return pd.DataFrame(rows)
