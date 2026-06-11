"""Tests de autenticación de la REST API (sin red: el verificador se simula o
se usa HS256 con un secreto de prueba)."""
import time

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

import api
import auth


@pytest.fixture()
def client():
    return TestClient(api.app)


def test_health_es_publico(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.parametrize("method,path,body", [
    ("post", "/chat", {"message": "hola"}),
    ("post", "/export/csv", {"columns": ["a"], "rows": [[1]]}),
    ("get", "/insights", None),
    ("get", "/insights/markdown", None),
    ("get", "/insights/narrative", None),
    ("delete", "/session/x", None),
])
def test_endpoints_requieren_token(client, method, path, body):
    r = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
    assert r.status_code == 401


def test_token_basura_es_401(client):
    r = client.post("/export/csv", json={"columns": ["a"], "rows": [[1]]},
                    headers={"Authorization": "Bearer no-soy-un-jwt"})
    assert r.status_code == 401


def test_token_hs256_valido(client, monkeypatch):
    """Camino HS256 (legacy) de verify_token, firmado con un secreto de prueba."""
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "secreto-de-test")
    token = pyjwt.encode(
        {"sub": "11111111-1111-1111-1111-111111111111", "email": "test@saior.demo",
         "aud": "authenticated", "exp": int(time.time()) + 300},
        "secreto-de-test", algorithm="HS256",
    )
    r = client.post("/export/csv", json={"columns": ["a"], "rows": [[1]]},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")


def test_token_hs256_expirado_es_401(client, monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "secreto-de-test")
    token = pyjwt.encode(
        {"sub": "x", "aud": "authenticated", "exp": int(time.time()) - 10},
        "secreto-de-test", algorithm="HS256",
    )
    r = client.get("/insights", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_dependency_override_da_acceso(client):
    """Con la dependencia simulada, el endpoint responde (wiring correcto)."""
    api.app.dependency_overrides[auth.get_current_user] = lambda: auth.AuthUser(
        id="22222222-2222-2222-2222-222222222222", email="fake@saior.demo")
    try:
        r = client.post("/export/csv", json={"columns": ["a"], "rows": [[1]]})
        assert r.status_code == 200
    finally:
        api.app.dependency_overrides.clear()
