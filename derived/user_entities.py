"""User-constructed entity runtime. See SPEC §3.6 / CLAUDE.md §5."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pandas as pd

from backend.db import get_connection
from derived.base import ComputationResult, InputRef

_SCHEMA_READY = False
SUPPORTED_OPS = {"weighted_sum", "threshold", "trend_direction", "rolling_average"}


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    con = get_connection(read_only=False)
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS user_entities (
              user_entity_id    VARCHAR PRIMARY KEY,
              name              VARCHAR,
              created_at        TIMESTAMP,
              composition_spec  VARCHAR
            )
            """
        )
    finally:
        con.close()
    _SCHEMA_READY = True


def _validate(spec: dict) -> None:
    op = spec.get("operation")
    if op not in SUPPORTED_OPS:
        raise ValueError(f"unsupported operation: {op!r}")
    inputs = spec.get("inputs") or []
    if not inputs:
        raise ValueError("at least one input required")
    if op == "weighted_sum":
        for i in inputs:
            if "entity_type" not in i or "weight" not in i:
                raise ValueError("weighted_sum inputs need entity_type + weight")


def create(name: str, composition_spec: dict) -> str:
    _ensure_schema()
    _validate(composition_spec)
    uid = str(uuid.uuid4())
    con = get_connection(read_only=False)
    try:
        con.execute(
            "INSERT INTO user_entities VALUES (?, ?, ?, ?)",
            [uid, name, datetime.utcnow(),
             json.dumps(composition_spec, default=str)],
        )
    finally:
        con.close()
    return uid


def list_all() -> list[dict]:
    _ensure_schema()
    con = get_connection(read_only=True)
    try:
        rows = con.execute(
            "SELECT user_entity_id, name, created_at, composition_spec "
            "FROM user_entities ORDER BY created_at DESC"
        ).fetchall()
    finally:
        con.close()
    return [{
        "user_entity_id": r[0], "name": r[1], "created_at": r[2],
        "composition_spec": json.loads(r[3]),
    } for r in rows]


def delete(uid: str) -> None:
    _ensure_schema()
    con = get_connection(read_only=False)
    try:
        con.execute("DELETE FROM user_entities WHERE user_entity_id = ?", [uid])
    finally:
        con.close()


def get(uid: str) -> dict:
    _ensure_schema()
    con = get_connection(read_only=True)
    try:
        row = con.execute(
            "SELECT user_entity_id, name, created_at, composition_spec "
            "FROM user_entities WHERE user_entity_id = ?", [uid]
        ).fetchone()
    finally:
        con.close()
    if not row:
        raise KeyError(uid)
    return {"user_entity_id": row[0], "name": row[1], "created_at": row[2],
            "composition_spec": json.loads(row[3])}


def compute(user_entity_id: str, target_id: str,
            at_time: datetime) -> ComputationResult:
    """Always target-scoped per CLAUDE.md §5."""
    from derived import REGISTRY
    spec = get(user_entity_id)
    composition = spec["composition_spec"]
    op = composition["operation"]
    inputs_spec = composition["inputs"]
    params = composition.get("params", {})

    component_values = {}
    inputs_ref: dict[str, InputRef] = {}
    for i, inp in enumerate(inputs_spec):
        et = inp["entity_type"]
        if et not in REGISTRY:
            raise ValueError(f"unknown entity_type in user entity: {et}")
        r = REGISTRY[et].compute_cached(target_id, at_time)
        val = r.value if isinstance(r.value, (int, float)) else 0.0
        component_values[f"{et}_{i}"] = val
        inputs_ref[f"{et}_{i}"] = InputRef(
            r.computation_id or "", "computations",
            {"kind": "child_computation", "entity_type": et,
             "entity_id": target_id, "at_time": str(at_time)}, 1)

    if op == "weighted_sum":
        weights = [float(i["weight"]) for i in inputs_spec]
        values = list(component_values.values())
        score = sum(w * v for w, v in zip(weights, values))
        result_value: float | dict = round(score, 6)
        components = {**component_values, "weights": weights,
                       "user_entity_id": user_entity_id}
    elif op == "threshold":
        score = next(iter(component_values.values()))
        thr = float(params.get("threshold", 0.5))
        result_value = bool(score >= thr)
        components = {**component_values, "threshold": thr}
    elif op == "rolling_average":
        et = inputs_spec[0]["entity_type"]
        win = int(params.get("window_days", 30))
        hist = REGISTRY[et].history(
            target_id, at_time - timedelta(days=win), at_time, "daily")
        result_value = float(hist["value"].mean()) if not hist.empty else 0.0
        components = {"window_days": win, "n_samples": int(len(hist)),
                       **component_values}
    elif op == "trend_direction":
        et = inputs_spec[0]["entity_type"]
        win = int(params.get("window_days", 30))
        hist = REGISTRY[et].history(
            target_id, at_time - timedelta(days=win), at_time, "daily")
        if len(hist) < 2:
            result_value = 0.0
            components = {"n_samples": int(len(hist))}
        else:
            xs = pd.Series(range(len(hist)), dtype=float)
            ys = hist["value"].astype(float).reset_index(drop=True)
            slope = float(((xs - xs.mean()) * (ys - ys.mean())).sum() /
                          max(((xs - xs.mean()) ** 2).sum(), 1e-9))
            result_value = float(1.0 if slope > 0 else (-1.0 if slope < 0 else 0.0))
            components = {"slope": slope, "n_samples": int(len(hist))}
    else:
        raise ValueError(f"unsupported op: {op}")

    return ComputationResult(
        value=result_value,
        components=components,
        inputs=inputs_ref,
        formula_version="user_v1.0.0",
        entity_type=f"user:{user_entity_id}",
        entity_id=target_id,
        at_time=at_time,
        formula_name=f"user/{op}",
    )
