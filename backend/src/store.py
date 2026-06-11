"""Persistencia de conversaciones en Supabase (schema app).

El backend se conecta con el rol de servicio y scopea TODA operación por el
user_id verificado del JWT — nunca por IDs del body. RLS queda como segunda
línea de defensa para accesos directos.

Dos representaciones por conversación, a propósito:
  - conversations.api_history : mensajes crudos del SDK de Anthropic → continuar el chat
  - messages.content          : segments renderizables → replay fiel en la UI
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@lru_cache(maxsize=1)
def _pool() -> ConnectionPool:
    return ConnectionPool(
        os.environ["SUPABASE_DB_URL"],
        min_size=0,
        max_size=5,
        kwargs={"autocommit": True},
        open=True,
    )


def make_title(message: str, limit: int = 48) -> str:
    text = " ".join(message.split())
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def create_conversation(user_id: str, title: str) -> str:
    with _pool().connection() as conn:
        row = conn.execute(
            "insert into app.conversations (user_id, title) values (%s, %s) returning id",
            (user_id, title),
        ).fetchone()
    return str(row[0])


def list_conversations(user_id: str, limit: int = 50) -> list[dict]:
    with _pool().connection() as conn:
        rows = conn.execute(
            """select id, title, created_at, updated_at
               from app.conversations where user_id = %s
               order by updated_at desc limit %s""",
            (user_id, limit),
        ).fetchall()
    return [
        {"id": str(r[0]), "title": r[1],
         "created_at": r[2].isoformat(), "updated_at": r[3].isoformat()}
        for r in rows
    ]


def get_api_history(user_id: str, conversation_id: str) -> list | None:
    """Historial crudo para continuar el chat. None si no existe o no es del usuario."""
    with _pool().connection() as conn:
        row = conn.execute(
            "select api_history from app.conversations where id = %s and user_id = %s",
            (conversation_id, user_id),
        ).fetchone()
    return row[0] if row else None


def get_messages(user_id: str, conversation_id: str) -> list[dict] | None:
    """Mensajes renderizables para el replay. None si la conversación no es del usuario."""
    with _pool().connection() as conn:
        owned = conn.execute(
            "select 1 from app.conversations where id = %s and user_id = %s",
            (conversation_id, user_id),
        ).fetchone()
        if not owned:
            return None
        rows = conn.execute(
            """select role, content, created_at from app.messages
               where conversation_id = %s order by id""",
            (conversation_id,),
        ).fetchall()
    return [{"role": r[0], "content": r[1], "created_at": r[2].isoformat()} for r in rows]


def append_turn(
    user_id: str,
    conversation_id: str,
    user_text: str,
    assistant_content: dict[str, Any],
    api_history: list,
) -> None:
    """Persiste un turno completo (pregunta + respuesta) y el historial actualizado."""
    with _pool().connection() as conn, conn.transaction():
        owned = conn.execute(
            "select 1 from app.conversations where id = %s and user_id = %s",
            (conversation_id, user_id),
        ).fetchone()
        if not owned:
            raise PermissionError("conversación ajena o inexistente")
        conn.execute(
            "insert into app.messages (conversation_id, role, content) values (%s, 'user', %s)",
            (conversation_id, Jsonb({"text": user_text})),
        )
        conn.execute(
            "insert into app.messages (conversation_id, role, content) values (%s, 'assistant', %s)",
            (conversation_id, Jsonb(assistant_content)),
        )
        conn.execute(
            "update app.conversations set api_history = %s, updated_at = now() where id = %s",
            (Jsonb(api_history), conversation_id),
        )


def delete_conversation(user_id: str, conversation_id: str) -> bool:
    with _pool().connection() as conn:
        row = conn.execute(
            "delete from app.conversations where id = %s and user_id = %s returning id",
            (conversation_id, user_id),
        ).fetchone()
    return row is not None


def rename_conversation(user_id: str, conversation_id: str, title: str) -> bool:
    with _pool().connection() as conn:
        row = conn.execute(
            """update app.conversations set title = %s, updated_at = now()
               where id = %s and user_id = %s returning id""",
            (title[:120], conversation_id, user_id),
        ).fetchone()
    return row is not None
