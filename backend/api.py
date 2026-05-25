"""Backend API surface consumed by Streamlit pages. See SPEC.md Section 6.

All functions below are stubs. Implement in Phase 1+.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd


def get_cursor() -> datetime:
    raise NotImplementedError


def set_cursor(at_time: datetime) -> None:
    raise NotImplementedError


def get_data_layer_summary(at_time: datetime) -> dict:
    raise NotImplementedError


def query_data_layer(
    table: str, filter: dict, at_time: datetime, limit: int
) -> pd.DataFrame:
    raise NotImplementedError


def list_entities(entity_type: str) -> list[str]:
    raise NotImplementedError


def get_entity(entity_type: str, entity_id: str, at_time: datetime) -> Any:
    raise NotImplementedError


def get_entity_history(
    entity_type: str,
    entity_id: str,
    from_time: datetime,
    to_time: datetime,
    granularity: str,
) -> pd.DataFrame:
    raise NotImplementedError


def decompose(computation_id: str, depth: int = 1) -> dict:
    raise NotImplementedError


def construct_entity(name: str, composition_spec: dict) -> str:
    raise NotImplementedError


def list_user_entities() -> list[dict]:
    raise NotImplementedError


def delete_user_entity(user_entity_id: str) -> None:
    raise NotImplementedError


def compute_user_entity(
    user_entity_id: str, target_id: str, at_time: datetime
) -> Any:
    raise NotImplementedError


def list_products() -> list[dict]:
    raise NotImplementedError


def simulate_product(
    product_id: str, parameters: dict, at_time: datetime
) -> Any:
    raise NotImplementedError


def get_product_default_parameters(product_id: str) -> dict:
    raise NotImplementedError


def get_provenance(table: str) -> str:
    raise NotImplementedError


def get_provenance_summary() -> dict:
    raise NotImplementedError
