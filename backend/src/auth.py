"""Validación local de JWTs de Supabase Auth — sin viaje de red por request.

El frontend manda `Authorization: Bearer <access_token>`; aquí se valida la firma
contra el JWKS del proyecto (ES256/RS256, cacheado 1h). Si el proyecto usara el
esquema legacy (HS256), se acepta con SUPABASE_JWT_SECRET configurado.

El user_id (claim `sub`) que sale de aquí es la ÚNICA identidad que el backend
usa para scoping de conversaciones: jamás se confía en IDs venidos del body.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import HTTPException, Request

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str


@lru_cache(maxsize=1)
def _jwks() -> jwt.PyJWKSet:
    """JWKS del proyecto, cacheado. Se trae con httpx (certifi) en lugar del
    PyJWKClient de urllib, que en macOS no encuentra los certificados CA."""
    base = os.environ["SUPABASE_PROJECT_URL"].rstrip("/")
    data = httpx.get(f"{base}/auth/v1/.well-known/jwks.json", timeout=10).json()
    return jwt.PyJWKSet.from_dict(data)


def _signing_key(token: str):
    kid = jwt.get_unverified_header(token).get("kid")
    for k in _jwks().keys:
        if k.key_id == kid:
            return k.key
    _jwks.cache_clear()  # rotación de llaves: refrescar una vez y reintentar
    for k in _jwks().keys:
        if k.key_id == kid:
            return k.key
    raise jwt.InvalidTokenError("kid del token no está en el JWKS del proyecto")


def verify_token(token: str) -> dict:
    """Devuelve los claims si el token es válido; lanza jwt.PyJWTError si no."""
    alg = jwt.get_unverified_header(token).get("alg", "")
    if alg in ("ES256", "RS256"):
        return jwt.decode(token, _signing_key(token), algorithms=[alg], audience="authenticated")
    if alg == "HS256":  # proyectos legacy
        secret = os.environ.get("SUPABASE_JWT_SECRET")
        if not secret:
            raise jwt.InvalidTokenError("token HS256 pero SUPABASE_JWT_SECRET no está configurado")
        return jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
    raise jwt.InvalidTokenError(f"algoritmo no soportado: {alg!r}")


async def get_current_user(request: Request) -> AuthUser:
    """Dependencia FastAPI: exige un Bearer token válido de Supabase."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Autenticación requerida")
    try:
        claims = verify_token(header[7:].strip())
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Token inválido: {e}") from e
    return AuthUser(id=claims["sub"], email=claims.get("email", ""))
