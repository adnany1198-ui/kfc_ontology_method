"""Backend API surface consumed by Streamlit pages. See SPEC.md Section 6."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pandas as pd

from backend import cursor
from backend.db import get_connection

_TABLE_PROVENANCE = {
    "pos_transactions": "observed",
    "pos_line_items": "observed",
    "menu_items": "observed",
    "store_summary": "observed",
    "ingredient_consumption_daily": "derived",
    "sku_recipe_mapping": "derived",
    "skus": "modelled",
    "recipes": "modelled",
    "ingredients": "modelled",
    "suppliers": "modelled",
    "nodes": "modelled",
    "purchase_orders": "modelled",
    "deliveries": "modelled",
    "invoices": "modelled",
    "payments": "modelled",
    "store_routing": "modelled",
    "computations": "derived",
    "computation_inputs": "derived",
    "user_entities": "derived",
}


# --- time + provenance ------------------------------------------------------

def get_cursor() -> datetime:
    return cursor.get()


def set_cursor(at_time: datetime) -> None:
    cursor.set(at_time)


def get_provenance(table: str) -> str:
    return _TABLE_PROVENANCE.get(table, "unknown")


def get_provenance_summary() -> dict:
    con = get_connection(read_only=True)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main'"
        ).fetchall()]
        out = {}
        for t in tables:
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            p = get_provenance(t)
            out.setdefault(p, {"tables": 0, "rows": 0})
            out[p]["tables"] += 1
            out[p]["rows"] += n
    finally:
        con.close()
    return out


# --- data layer summary -----------------------------------------------------

def get_data_layer_summary(at_time: datetime) -> dict:
    con = get_connection(read_only=True)
    try:
        observed_today = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(basket_value), 0) "
            "FROM pos_transactions "
            "WHERE CAST(transaction_timestamp AS DATE) = ?",
            [at_time.date()],
        ).fetchone()
        observed_to_date = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(basket_value), 0) "
            "FROM pos_transactions WHERE transaction_timestamp <= ?",
            [at_time],
        ).fetchone()
        derived_today = con.execute(
            "SELECT COUNT(DISTINCT ingredient_id), "
            "       COALESCE(SUM(consumed_qty), 0) "
            "FROM ingredient_consumption_daily WHERE date = ?",
            [at_time.date()],
        ).fetchone()
        modelled_outstanding_ap = con.execute(
            """
            SELECT COALESCE(SUM(i.amount_pkr), 0)
            FROM invoices i
            LEFT JOIN payments p ON p.invoice_id = i.invoice_id
                                AND p.payment_date <= ?
            WHERE i.invoice_date <= ? AND p.payment_id IS NULL
            """,
            [at_time.date(), at_time.date()],
        ).fetchone()[0]
        modelled_pay_next_7 = con.execute(
            """
            SELECT COALESCE(SUM(amount_pkr), 0)
            FROM invoices i
            WHERE i.due_date BETWEEN ? AND ?
              AND NOT EXISTS (SELECT 1 FROM payments p
                              WHERE p.invoice_id = i.invoice_id
                                AND p.payment_date <= ?)
            """,
            [at_time.date(), at_time.date() + pd.Timedelta(days=7),
             at_time.date()],
        ).fetchone()[0]
    finally:
        con.close()
    return {
        "observed_tx_today": observed_today[0],
        "observed_revenue_today": float(observed_today[1] or 0.0),
        "observed_tx_to_date": observed_to_date[0],
        "observed_revenue_to_date": float(observed_to_date[1] or 0.0),
        "derived_ingredient_count_today": derived_today[0],
        "derived_consumption_qty_today": float(derived_today[1] or 0.0),
        "modelled_ap_outstanding": float(modelled_outstanding_ap or 0.0),
        "modelled_pay_next_7": float(modelled_pay_next_7 or 0.0),
    }


def query_data_layer(table: str, filters: dict | None = None,
                     at_time: datetime | None = None,
                     limit: int = 100) -> pd.DataFrame:
    time_columns = {
        "pos_transactions": "transaction_timestamp",
        "pos_line_items": "transaction_timestamp",
        "ingredient_consumption_daily": "date",
        "purchase_orders": "po_date",
        "deliveries": "delivery_date",
        "invoices": "invoice_date",
        "payments": "payment_date",
    }
    con = get_connection(read_only=True)
    try:
        clauses, params = [], []
        if at_time is not None and table in time_columns:
            col = time_columns[table]
            clauses.append(f"{col} <= ?")
            params.append(at_time if "timestamp" in col else at_time.date())
        for k, v in (filters or {}).items():
            if isinstance(v, dict) and "op" in v:
                op = v["op"].lower()
                sql_op = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
                          "eq": "=", "ne": "!="}.get(op)
                if sql_op:
                    clauses.append(f"{k} {sql_op} ?")
                    params.append(v["value"])
                elif op == "in":
                    placeholders = ",".join(["?"] * len(v["value"]))
                    clauses.append(f"{k} IN ({placeholders})")
                    params.extend(v["value"])
            else:
                clauses.append(f"{k} = ?")
                params.append(v)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        df = con.execute(
            f"SELECT * FROM {table}{where} LIMIT {int(limit)}",
            params,
        ).fetchdf()
    finally:
        con.close()
    return df


# --- derived entities (filled in Phase 3) -----------------------------------

def list_entities(entity_type: str) -> list[str]:
    from derived import REGISTRY
    if entity_type not in REGISTRY:
        return []
    return REGISTRY[entity_type].list_targets()


def get_entity(entity_type: str, entity_id: str, at_time: datetime):
    from derived import REGISTRY
    if entity_type not in REGISTRY:
        raise ValueError(f"unknown entity_type: {entity_type}")
    return REGISTRY[entity_type].compute_cached(entity_id, at_time)


def get_entity_history(entity_type: str, entity_id: str,
                       from_time: datetime, to_time: datetime,
                       granularity: str = "daily") -> pd.DataFrame:
    from derived import REGISTRY
    if entity_type not in REGISTRY:
        return pd.DataFrame()
    return REGISTRY[entity_type].history(entity_id, from_time, to_time,
                                          granularity)


def decompose(computation_id: str, depth: int = 1) -> dict:
    from backend import lineage
    return lineage.decompose(computation_id, depth=depth)


# --- user entities ---------------------------------------------------------

def construct_entity(name: str, composition_spec: dict) -> str:
    from derived import user_entities
    return user_entities.create(name, composition_spec)


def list_user_entities() -> list[dict]:
    from derived import user_entities
    return user_entities.list_all()


def delete_user_entity(user_entity_id: str) -> None:
    from derived import user_entities
    user_entities.delete(user_entity_id)


def compute_user_entity(user_entity_id: str, target_id: str,
                        at_time: datetime):
    from derived import user_entities
    return user_entities.compute(user_entity_id, target_id, at_time)


# --- credit products -------------------------------------------------------

def list_products() -> list[dict]:
    from products import REGISTRY
    return [{"product_id": pid, "name": p.NAME,
             "default_parameters": p.DEFAULT_PARAMETERS,
             "score_input": p.SCORE_INPUT}
            for pid, p in REGISTRY.items()]


def simulate_product(product_id: str, parameters: dict, at_time: datetime):
    from products import REGISTRY
    if product_id not in REGISTRY:
        raise ValueError(f"unknown product_id: {product_id}")
    return REGISTRY[product_id].simulate(parameters, at_time)


def get_product_default_parameters(product_id: str) -> dict:
    from products import REGISTRY
    return dict(REGISTRY[product_id].DEFAULT_PARAMETERS)
