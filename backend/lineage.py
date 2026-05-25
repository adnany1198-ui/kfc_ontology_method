"""Lineage persistence and decomposition. See SPEC §3.5 / CLAUDE.md §3."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from backend.db import get_connection

if TYPE_CHECKING:
    from derived.base import ComputationResult

_SCHEMA_READY = False


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    con = get_connection(read_only=False)
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS computations (
              computation_id        VARCHAR PRIMARY KEY,
              entity_type           VARCHAR,
              entity_id             VARCHAR,
              computed_at           TIMESTAMP,
              at_time               TIMESTAMP,
              formula_name          VARCHAR,
              formula_version       VARCHAR,
              output_value_numeric  DOUBLE,
              output_value_json     VARCHAR,
              components_json       VARCHAR,
              is_stale              BOOLEAN DEFAULT FALSE
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS computation_inputs (
              computation_id        VARCHAR,
              input_name            VARCHAR,
              input_value_numeric   DOUBLE,
              input_value_json      VARCHAR,
              child_computation_id  VARCHAR,
              source_table          VARCHAR,
              source_filter         VARCHAR,
              source_row_count      INTEGER
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_comp_key "
            "ON computations (entity_type, entity_id, at_time, formula_version)"
        )
    finally:
        con.close()
    _SCHEMA_READY = True


def store(result: "ComputationResult") -> str:
    _ensure_schema()
    cid = str(uuid.uuid4())
    is_scalar = isinstance(result.value, (int, float))
    con = get_connection(read_only=False)
    try:
        con.execute(
            "INSERT INTO computations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                cid,
                result.entity_type,
                result.entity_id,
                datetime.utcnow(),
                result.at_time,
                result.formula_name,
                result.formula_version,
                float(result.value) if is_scalar else None,
                None if is_scalar else json.dumps(result.value, default=_json_default),
                json.dumps(result.components, default=_json_default),
                False,
            ],
        )
        for name, ref in (result.inputs or {}).items():
            child_id = ref.value if (isinstance(ref.source_filter, dict)
                                     and ref.source_filter.get("kind") ==
                                     "child_computation") else None
            scalar = (isinstance(ref.value, (int, float))
                      and not isinstance(ref.value, bool))
            con.execute(
                "INSERT INTO computation_inputs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    cid,
                    name,
                    float(ref.value) if scalar and child_id is None else None,
                    None if (scalar and child_id is None) else
                    json.dumps(ref.value, default=_json_default),
                    child_id,
                    ref.source_table,
                    json.dumps(ref.source_filter, default=_json_default)
                    if isinstance(ref.source_filter, dict) else ref.source_filter,
                    int(ref.source_row_count),
                ],
            )
    finally:
        con.close()
    return cid


def lookup(entity_type: str, entity_id: str, at_time: datetime,
           formula_version: str) -> "ComputationResult | None":
    _ensure_schema()
    con = get_connection(read_only=True)
    try:
        row = con.execute(
            """
            SELECT computation_id, output_value_numeric, output_value_json,
                   components_json, formula_name
            FROM computations
            WHERE entity_type = ? AND entity_id = ? AND at_time = ?
              AND formula_version = ? AND NOT is_stale
            ORDER BY computed_at DESC LIMIT 1
            """,
            [entity_type, entity_id, at_time, formula_version],
        ).fetchone()
    finally:
        con.close()
    if not row:
        return None
    from derived.base import ComputationResult
    cid, num, js, components_js, fname = row
    value = num if num is not None else (json.loads(js) if js else None)
    return ComputationResult(
        value=value,
        components=json.loads(components_js) if components_js else {},
        inputs={},
        formula_version=formula_version,
        entity_type=entity_type,
        entity_id=entity_id,
        at_time=at_time,
        computation_id=cid,
        formula_name=fname,
    )


def decompose(computation_id: str, depth: int = 1) -> dict:
    _ensure_schema()
    con = get_connection(read_only=True)
    try:
        comp = con.execute(
            "SELECT entity_type, entity_id, output_value_numeric, "
            "       output_value_json, formula_version, components_json "
            "FROM computations WHERE computation_id = ?",
            [computation_id],
        ).fetchone()
        if not comp:
            return {}
        et, eid, num, js, fver, cjs = comp
        value = num if num is not None else (json.loads(js) if js else None)
        inputs = con.execute(
            "SELECT input_name, input_value_numeric, input_value_json, "
            "       child_computation_id, source_table, source_filter, "
            "       source_row_count "
            "FROM computation_inputs WHERE computation_id = ?",
            [computation_id],
        ).fetchall()
    finally:
        con.close()

    children = []
    for name, n, vjs, child_id, table, filt, rows in inputs:
        v = n if n is not None else (json.loads(vjs) if vjs else None)
        if child_id and depth > 1:
            children.append({
                "input_name": name,
                "kind": "computation",
                **decompose(child_id, depth=depth - 1),
            })
        elif child_id:
            children.append({
                "input_name": name, "kind": "computation",
                "child_computation_id": child_id, "value": v,
            })
        else:
            children.append({
                "input_name": name,
                "kind": "leaf",
                "value": v,
                "source_table": table,
                "source_filter": json.loads(filt) if filt and filt.startswith("{") else filt,
                "source_row_count": rows,
            })

    return {
        "computation_id": computation_id,
        "entity_type": et,
        "entity_id": eid,
        "value": value,
        "formula_version": fver,
        "components": json.loads(cjs) if cjs else {},
        "children": children,
    }


def invalidate(entity_type: str | None = None) -> None:
    _ensure_schema()
    con = get_connection(read_only=False)
    try:
        if entity_type:
            con.execute("UPDATE computations SET is_stale = TRUE "
                        "WHERE entity_type = ?", [entity_type])
        else:
            con.execute("UPDATE computations SET is_stale = TRUE")
    finally:
        con.close()


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)
