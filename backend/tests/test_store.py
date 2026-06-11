"""Integración del store de conversaciones contra Supabase real.

Usa a los usuarios demo sembrados (juan y mariana) y limpia todo lo que crea.
Se omite si no hay SUPABASE_DB_URL configurada.
"""
import os

import pytest

import store

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"), reason="requiere SUPABASE_DB_URL"
)


@pytest.fixture(scope="module")
def demo_user_ids():
    """IDs reales de juan y mariana (auth.users), para respetar la FK."""
    with store._pool().connection() as conn:
        rows = conn.execute(
            "select email, id from auth.users where email in ('juan@saior.demo','mariana@saior.demo')"
        ).fetchall()
    ids = {r[0]: str(r[1]) for r in rows}
    assert len(ids) == 2, "corre scripts/seed_users.py primero"
    return ids["juan@saior.demo"], ids["mariana@saior.demo"]


@pytest.fixture()
def conversation(demo_user_ids):
    juan, _ = demo_user_ids
    conv_id = store.create_conversation(juan, "Test de persistencia")
    yield juan, conv_id
    store.delete_conversation(juan, conv_id)


def test_ciclo_completo_de_turno(conversation):
    juan, conv_id = conversation

    assert store.get_api_history(juan, conv_id) == []

    api_history = [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": [{"type": "text", "text": "respuesta"}]},
    ]
    assistant = {"segments": [{"kind": "text", "text": "respuesta"}], "tools": [],
                 "usage": {"input_tokens": 10, "output_tokens": 5}}
    store.append_turn(juan, conv_id, "hola", assistant, api_history)

    # continuar: el historial crudo vuelve íntegro
    assert store.get_api_history(juan, conv_id) == api_history

    # replay: los mensajes renderizables vuelven en orden
    msgs = store.get_messages(juan, conv_id)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == {"text": "hola"}
    assert msgs[1]["content"]["segments"][0]["text"] == "respuesta"

    # listado del usuario incluye la conversación
    assert any(c["id"] == conv_id for c in store.list_conversations(juan))


def test_aislamiento_entre_usuarios(conversation, demo_user_ids):
    """Mariana no puede ver, escribir ni borrar conversaciones de Juan."""
    juan, conv_id = conversation
    _, mariana = demo_user_ids

    assert store.get_api_history(mariana, conv_id) is None
    assert store.get_messages(mariana, conv_id) is None
    assert not any(c["id"] == conv_id for c in store.list_conversations(mariana))
    assert store.delete_conversation(mariana, conv_id) is False
    assert store.rename_conversation(mariana, conv_id, "hackeado") is False
    with pytest.raises(PermissionError):
        store.append_turn(mariana, conv_id, "x", {"segments": [], "tools": []}, [])

    # y la conversación de Juan sigue intacta
    assert store.get_api_history(juan, conv_id) == []


def test_rename_y_delete(demo_user_ids):
    juan, _ = demo_user_ids
    conv_id = store.create_conversation(juan, "para renombrar")
    assert store.rename_conversation(juan, conv_id, "renombrada") is True
    assert any(c["title"] == "renombrada" for c in store.list_conversations(juan)
               if c["id"] == conv_id)
    assert store.delete_conversation(juan, conv_id) is True
    assert store.get_messages(juan, conv_id) is None
