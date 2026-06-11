"""ETL: carga los datos del caso a Supabase (schema ops) y verifica contra los goldens.

Lee los parquet de data/processed/ (ya validados por la golden suite). Si necesitas
partir del Excel crudo, corre antes:  python src/prepare_data.py data/raw/dummydata.xlsx

Idempotente: TRUNCATE + COPY dentro de una única transacción; si la verificación
final no cuadra, rollback completo.

Ejecutar desde backend/:  .venv/bin/python scripts/load_supabase.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
load_dotenv(ROOT / ".env")

# Verificaciones post-carga: si algo no cuadra, NADA queda cargado.
EXPECTED = {
    "metrics_rows": 104_490,
    "orders_rows": 11_178,
    "catalog_rows": 14,
    "out_of_range_flags": 253,
    # spot-checks golden (mismos valores que tests/test_golden_queries.py)
    "po_mx_wealthy_wk0": 0.9043,   # avg Perfect Orders MX Wealthy semana 0
    "lp_ec_wk0_ok": 0.1486,        # avg Lead Penetration EC semana 0, flags excluidos
}


def _none(v):
    return None if (v is None or (isinstance(v, float) and math.isnan(v))) else v


def copy_df(conn: psycopg.Connection, table: str, df: pd.DataFrame, cols: list[str]) -> None:
    with conn.cursor() as cur:
        with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
            for row in df[ [c.upper() if c.upper() in df.columns else c for c in cols] ].itertuples(index=False):
                cp.write_row(tuple(_none(v) for v in row))


def main() -> int:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("Falta SUPABASE_DB_URL en backend/.env")
        return 1

    t0 = time.time()
    metrics = pd.read_parquet(DATA / "metrics_long.parquet")
    orders = pd.read_parquet(DATA / "orders_long.parquet")
    catalog = json.loads((ROOT / "src" / "metrics_catalog.json").read_text())

    cat_rows = pd.DataFrame(
        [
            {
                "metric": name,
                "definition": spec.get("definition"),
                "format": spec.get("format"),
                "higher_is_better": spec.get("higher_is_better"),
                "valid_lo": (spec.get("valid_range") or [None, None])[0],
                "valid_hi": (spec.get("valid_range") or [None, None])[1],
                "caveat": spec.get("caveat"),
            }
            for name, spec in catalog["metrics"].items()
        ]
    )

    with psycopg.connect(db_url) as conn:
        with conn.transaction():
            conn.execute("truncate ops.metrics_long, ops.orders_long, ops.metric_catalog")

            copy_df(conn, "ops.metrics_long", metrics,
                    ["country", "city", "zone", "zone_type", "zone_prioritization",
                     "metric", "week", "value", "quality_flag"])
            copy_df(conn, "ops.orders_long", orders, ["country", "city", "zone", "week", "value"])
            copy_df(conn, "ops.metric_catalog", cat_rows, list(cat_rows.columns))

            # ------------------------------------------------ verificación o rollback
            q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
            checks = {
                "metrics_rows": q("select count(*) from ops.metrics_long"),
                "orders_rows": q("select count(*) from ops.orders_long"),
                "catalog_rows": q("select count(*) from ops.metric_catalog"),
                "out_of_range_flags": q(
                    "select count(*) from ops.metrics_long where quality_flag <> 'OK'"),
                "po_mx_wealthy_wk0": float(q(
                    "select round(avg(value)::numeric, 4) from ops.metrics_long "
                    "where metric='Perfect Orders' and country='MX' "
                    "and zone_type='Wealthy' and week=0 and value is not null")),
                "lp_ec_wk0_ok": float(q(
                    "select round(avg(value)::numeric, 4) from ops.metrics_long "
                    "where metric='Lead Penetration' and country='EC' and week=0 "
                    "and quality_flag='OK' and value is not null")),
            }
            failures = {k: (checks[k], v) for k, v in EXPECTED.items() if checks[k] != v}
            if failures:
                print("VERIFICACIÓN FALLÓ (rollback):")
                for k, (got, want) in failures.items():
                    print(f"  {k}: obtenido {got}, esperado {want}")
                raise SystemExit(1)

        conn.execute("analyze ops.metrics_long; analyze ops.orders_long")
        conn.commit()

    for k, v in EXPECTED.items():
        print(f"  ✓ {k} = {v}")
    print(f"carga verificada en {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
