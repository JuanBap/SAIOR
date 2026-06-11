"""Siembra los usuarios demo en Supabase Auth (Admin API, idempotente).

Usuarios: juan@saior.demo · mariana@saior.demo · daniel@saior.demo
Password: variable DEMO_USERS_PASSWORD en backend/.env (no se imprime).

Ejecutar desde backend/:  .venv/bin/python scripts/seed_users.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DEMO_USERS = [
    ("juan@saior.demo", "Juan"),
    ("mariana@saior.demo", "Mariana"),
    ("daniel@saior.demo", "Daniel"),
]


def main() -> int:
    url = os.environ["SUPABASE_PROJECT_URL"].rstrip("/")
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    password = os.environ.get("DEMO_USERS_PASSWORD")
    if not password:
        print("Falta DEMO_USERS_PASSWORD en backend/.env")
        return 1

    headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
    failures = 0
    for email, name in DEMO_USERS:
        r = httpx.post(
            f"{url}/auth/v1/admin/users",
            headers=headers,
            json={
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"name": name},
            },
            timeout=15,
        )
        if r.status_code in (200, 201):
            print(f"  + {email} creado")
        elif r.status_code == 422 and "exists" in r.text:
            print(f"  = {email} ya existía")
        else:
            print(f"  x {email}: HTTP {r.status_code} {r.text[:120]}")
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
