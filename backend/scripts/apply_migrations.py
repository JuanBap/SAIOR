"""Aplica las migrations de supabase/migrations/ en orden, con ledger idempotente.

Ejecutar desde backend/:  .venv/bin/python scripts/apply_migrations.py
Requiere SUPABASE_DB_URL en backend/.env.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT.parent / "supabase" / "migrations"
load_dotenv(ROOT / ".env")

LEDGER = """
create table if not exists public.schema_migrations (
  name       text primary key,
  applied_at timestamptz not null default now()
)
"""


def main() -> int:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("Falta SUPABASE_DB_URL en backend/.env")
        return 1

    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        print(f"No hay migrations en {MIGRATIONS}")
        return 1

    with psycopg.connect(db_url) as conn:
        conn.execute(LEDGER)
        applied = {r[0] for r in conn.execute("select name from public.schema_migrations")}
        for f in files:
            if f.name in applied:
                print(f"  = {f.name} (ya aplicada)")
                continue
            print(f"  + {f.name} ...", end=" ")
            with conn.transaction():
                conn.execute(f.read_text())
                conn.execute("insert into public.schema_migrations (name) values (%s)", (f.name,))
            print("OK")
        conn.commit()
    print("migrations al día")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
