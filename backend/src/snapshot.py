"""Snapshot de datos: Supabase → DataFrames en memoria, con fallback a parquet local.

Única fuente de verdad: ops.* en Supabase (cargado por scripts/load_supabase.py).
Al arrancar el backend se trae todo a pandas (~104k filas, 2-4s) y las herramientas
del nivel 1 operan en memoria con la misma latencia de siempre.

Resiliencia de demo: si Supabase no responde, cae al parquet commiteado (idéntico
contenido, verificado por el ETL) y /health lo reporta como "fallback-parquet".
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
load_dotenv(ROOT / ".env")

_STATE = {"source": "uninitialized"}

# Aliases a MAYÚSCULAS: los DataFrames conservan el shape histórico del engine.
_METRICS_SQL = """
select country as "COUNTRY", city as "CITY", zone as "ZONE",
       zone_type as "ZONE_TYPE", zone_prioritization as "ZONE_PRIORITIZATION",
       metric as "METRIC", week as "WEEK", value as "VALUE",
       quality_flag as "QUALITY_FLAG"
from ops.metrics_long
"""
_ORDERS_SQL = """
select country as "COUNTRY", city as "CITY", zone as "ZONE",
       week as "WEEK", value as "VALUE"
from ops.orders_long
"""


def _read_sql(conn, sql: str) -> pd.DataFrame:
    cur = conn.execute(sql)
    cols = [d.name for d in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=cols)
    df["WEEK"] = df["WEEK"].astype("int64")
    df["VALUE"] = pd.to_numeric(df["VALUE"])
    return df


def _from_supabase() -> tuple[pd.DataFrame, pd.DataFrame]:
    import psycopg

    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL no configurada")
    with psycopg.connect(url, connect_timeout=6) as conn:
        return _read_sql(conn, _METRICS_SQL), _read_sql(conn, _ORDERS_SQL)


@lru_cache(maxsize=1)
def _load() -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        metrics, orders = _from_supabase()
        _STATE["source"] = "supabase"
    except Exception as e:  # noqa: BLE001 — cualquier fallo de red/credencial → fallback
        _STATE["source"] = f"fallback-parquet ({type(e).__name__})"
        metrics = pd.read_parquet(DATA / "metrics_long.parquet")
        orders = pd.read_parquet(DATA / "orders_long.parquet")
    return metrics, orders


def get_metrics() -> pd.DataFrame:
    return _load()[0]


def get_orders() -> pd.DataFrame:
    return _load()[1]


def source() -> str:
    _load()
    return _STATE["source"]
