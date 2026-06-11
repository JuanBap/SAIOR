"""Guardia del nivel 2: valida (AST), ejecuta (rol read-only) y audita el SQL
que genera el agente cuando ningún tool tipado cubre la pregunta.

Tres muros independientes:
  1. Validación AST (sqlglot): un solo SELECT, solo tablas de ops.*, sin funciones
     de sistema, LIMIT ≤ 500 inyectado/clampeado.
  2. Ejecución con SET LOCAL ROLE claude_readonly + statement_timeout 5s: aunque
     algo pasara el muro 1, Postgres no tiene grants fuera de SELECT en ops.
  3. Auditoría: todo intento (ok o rechazado) queda en app.query_log.
"""
from __future__ import annotations

import datetime as dt
import decimal
import time
import uuid as uuid_mod

import sqlglot
from sqlglot import exp

import store

ALLOWED_TABLES = {"metrics_long", "orders_long", "metric_catalog"}
MAX_LIMIT = 500
FORBIDDEN_FUNCTIONS = {
    "pg_sleep", "pg_sleep_for", "pg_sleep_until", "set_config", "current_setting",
    "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "lo_import", "lo_export",
    "dblink", "pg_terminate_backend", "pg_cancel_backend", "query_to_xml",
}
FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
    exp.Grant, exp.Command, exp.Set, exp.Transaction, exp.Merge, exp.Into,
)


class SQLGuardError(ValueError):
    """SQL rechazado por el validador (antes de tocar la base)."""


def validate(sql: str) -> str:
    """Devuelve el SQL normalizado y acotado, o lanza SQLGuardError."""
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except sqlglot.errors.ParseError as e:
        raise SQLGuardError(f"SQL no parseable: {str(e).splitlines()[0]}") from e
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise SQLGuardError("se permite exactamente un statement")
    tree = statements[0]

    if not isinstance(tree, (exp.Select, exp.Union)):
        raise SQLGuardError("solo se permiten consultas SELECT")
    for node_cls in FORBIDDEN_NODES:
        if tree.find(node_cls):
            raise SQLGuardError(f"operación no permitida: {node_cls.__name__.upper()}")

    # Tablas: solo ops.{metrics_long, orders_long, metric_catalog} (los alias de CTE no cuentan)
    cte_names = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name, schema = table.name, table.db
        if not schema and name in cte_names:
            continue
        if (schema or "ops") != "ops" or name not in ALLOWED_TABLES:
            ref = f"{schema}.{name}" if schema else name
            raise SQLGuardError(
                f"tabla no permitida: {ref} (solo ops.metrics_long, ops.orders_long, ops.metric_catalog)"
            )

    # Funciones de sistema prohibidas (las desconocidas parsean como Anonymous)
    for fn in tree.find_all(exp.Anonymous):
        if str(fn.this).lower() in FORBIDDEN_FUNCTIONS:
            raise SQLGuardError(f"función no permitida: {fn.this}")

    # LIMIT obligatorio y acotado
    if isinstance(tree, exp.Union):
        tree = exp.select("*").from_(tree.subquery("q"))
    limit_node = tree.args.get("limit")
    if limit_node is None:
        tree = tree.limit(MAX_LIMIT)
    else:
        try:
            current = int(limit_node.expression.this)
        except (TypeError, ValueError, AttributeError):
            current = MAX_LIMIT + 1
        if current > MAX_LIMIT:
            tree = tree.limit(MAX_LIMIT)

    return tree.sql(dialect="postgres")


def _jsonable(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, uuid_mod.UUID):
        return str(v)
    return v


def _audit(user_id, conversation_id, sql, ok, error, rows, ms) -> None:
    try:
        with store._pool().connection() as conn:
            conn.execute(
                """insert into app.query_log
                   (user_id, conversation_id, sql, ok, error, rows_returned, duration_ms)
                   values (%s, %s, %s, %s, %s, %s, %s)""",
                (user_id, conversation_id, sql[:8000], ok, error, rows, ms),
            )
    except Exception:  # noqa: BLE001 — la auditoría jamás rompe la respuesta
        pass


def execute(
    sql: str,
    *,
    purpose: str = "",
    user_id: str | None = None,
    conversation_id: str | None = None,
) -> dict:
    """Valida + ejecuta + audita. Devuelve {columns, rows, rowcount, sql} o {error}
    (el error vuelve al agente para que se corrija — self-healing)."""
    t0 = time.time()
    safe_sql = None
    try:
        safe_sql = validate(sql)
        with store._pool().connection() as conn, conn.transaction():
            conn.execute("set local role claude_readonly")
            conn.execute("set local statement_timeout = '5000'")
            cur = conn.execute(safe_sql)
            columns = [d.name for d in cur.description]
            rows = [[_jsonable(v) for v in r] for r in cur.fetchmany(MAX_LIMIT)]
        ms = int((time.time() - t0) * 1000)
        _audit(user_id, conversation_id, safe_sql, True, None, len(rows), ms)
        return {"columns": columns, "rows": rows, "rowcount": len(rows),
                "sql": safe_sql, "purpose": purpose}
    except SQLGuardError as e:
        _audit(user_id, conversation_id, sql, False, f"guard: {e}",
               None, int((time.time() - t0) * 1000))
        return {"error": f"SQL rechazado por el validador: {e}",
                "hint": "Escribe un único SELECT sobre ops.metrics_long / ops.orders_long / ops.metric_catalog."}
    except Exception as e:  # noqa: BLE001 — errores de Postgres → self-healing
        msg = str(e).splitlines()[0][:300]
        _audit(user_id, conversation_id, safe_sql or sql, False, msg,
               None, int((time.time() - t0) * 1000))
        return {"error": f"Error de Postgres: {msg}"}
