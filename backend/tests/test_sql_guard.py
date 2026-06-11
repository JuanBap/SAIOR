"""Tests del guardia del nivel 2: matriz de SQL permitido/bloqueado (validate, puro)
+ integración de execute contra Supabase (rol read-only + auditoría)."""
import os

import pytest

import sql_guard
from sql_guard import SQLGuardError, validate


# ------------------------------------------------------------- permitidos
def test_select_simple_inyecta_limit():
    out = validate("select country, value from ops.metrics_long where week = 0")
    assert "LIMIT 500" in out


def test_respeta_limit_menor():
    out = validate("select * from ops.metrics_long limit 10")
    assert "LIMIT 10" in out


def test_clampea_limit_excesivo():
    out = validate("select * from ops.metrics_long limit 99999")
    assert "LIMIT 500" in out


def test_cte_y_agregaciones():
    out = validate("""
        with co as (select * from ops.metrics_long where country = 'CO')
        select city, percentile_cont(0.5) within group (order by value) as mediana
        from co where metric = 'Perfect Orders' and week = 0 group by city
    """)
    assert out.upper().startswith("WITH")


def test_join_metrics_orders():
    out = validate("""
        select m.zone, m.value, o.value as orders
        from ops.metrics_long m join ops.orders_long o
          on m.country = o.country and m.city = o.city and m.zone = o.zone and m.week = o.week
        where m.metric = 'Perfect Orders' and m.week = 0
    """)
    assert "JOIN" in out.upper()


def test_nombre_sin_schema_se_permite():
    validate("select count(*) from metrics_long")


def test_union_se_acota():
    out = validate(
        "select zone from ops.metrics_long where week=0 "
        "union select zone from ops.orders_long where week=0"
    )
    assert "LIMIT 500" in out


# -------------------------------------------------------------- bloqueados
@pytest.mark.parametrize("bad_sql,motivo", [
    ("update ops.metrics_long set value = 0", "UPDATE"),
    ("delete from ops.metrics_long", "DELETE"),
    ("drop table ops.metrics_long", "DROP"),
    ("create table ops.x (i int)", "CREATE"),
    ("insert into ops.metrics_long values (1)", "INSERT"),
    ("select 1; select 2", "multi-statement"),
    ("select * from pg_catalog.pg_tables", "pg_catalog"),
    ("select * from information_schema.tables", "information_schema"),
    ("select * from app.conversations", "schema app"),
    ("select * from auth.users", "schema auth"),
    ("select * from public.schema_migrations", "schema public"),
    ("select pg_sleep(60)", "pg_sleep"),
    ("select current_setting('server_version')", "current_setting"),
    ("select value into temp_t from ops.metrics_long", "SELECT INTO"),
    ("grant select on ops.metrics_long to anon", "GRANT"),
    ("esto no es sql", "no parseable"),
])
def test_sql_bloqueado(bad_sql, motivo):
    with pytest.raises(SQLGuardError):
        validate(bad_sql)


# ------------------------------------------------- integración (Supabase real)
pytestmark_db = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"), reason="requiere SUPABASE_DB_URL"
)


@pytestmark_db
def test_execute_mediana_por_ciudad():
    r = sql_guard.execute(
        "select city, percentile_cont(0.5) within group (order by value) as mediana "
        "from ops.metrics_long where metric = 'Perfect Orders' and country = 'CO' "
        "and week = 0 and quality_flag = 'OK' group by city order by mediana limit 5",
        purpose="test: mediana por ciudad",
    )
    assert "error" not in r
    assert r["columns"] == ["city", "mediana"]
    assert 0 < r["rowcount"] <= 5
    assert all(isinstance(row[1], float) for row in r["rows"])


@pytestmark_db
def test_execute_rechaza_y_audita_update():
    r = sql_guard.execute("update ops.metrics_long set value = 0", purpose="test malicioso")
    assert "error" in r and "validador" in r["error"]
    # quedó auditado como rechazado
    import store
    with store._pool().connection() as conn:
        row = conn.execute(
            "select ok, error from app.query_log order by id desc limit 1"
        ).fetchone()
    assert row[0] is False and "guard" in row[1]


@pytestmark_db
def test_execute_error_de_postgres_vuelve_al_agente():
    r = sql_guard.execute(
        "select columna_inexistente from ops.metrics_long", purpose="test self-healing"
    )
    assert "error" in r and "Postgres" in r["error"]
