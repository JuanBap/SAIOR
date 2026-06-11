"""API FastAPI — Sistema de Análisis Inteligente Rappi.

Expone el agente conversacional vía streaming SSE, la persistencia de
conversaciones por usuario (Supabase) y utilidades de exportación.

Ejecutar (desde backend/src):
    uvicorn api:app --reload --port 8000
"""
from __future__ import annotations

import csv
import io
import json
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))
load_dotenv(SRC.parent / ".env")  # backend/.env

import os  # noqa: E402  (después de load_dotenv para que ANTHROPIC_MODEL ya esté disponible)

import store  # noqa: E402
from agent import stream_agent  # noqa: E402
from auth import AuthUser, get_current_user  # noqa: E402
from insights.report import build_report, narrate, to_markdown  # noqa: E402

app = FastAPI(title="Rappi Insights API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None


class RenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


class ExportRequest(BaseModel):
    columns: list[str]
    rows: list[list]
    filename: str = "export.csv"


@app.get("/health")
def health() -> dict:
    import snapshot

    return {"status": "ok", "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            "snapshot": snapshot.source()}


def _require_uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail="Conversación no encontrada")


class _TurnAccumulator:
    """Reconstruye, en el servidor, el mismo payload renderizable que arma la UI
    (segments + tools) para persistirlo y poder hacer replay fiel al recargar."""

    def __init__(self) -> None:
        self.segments: list[dict] = []
        self.tools: list[dict] = []

    def feed(self, ev: dict) -> None:
        t = ev.get("type")
        if t == "token":
            if self.segments and self.segments[-1]["kind"] == "text":
                self.segments[-1]["text"] += ev["text"]
            else:
                self.segments.append({"kind": "text", "text": ev["text"]})
        elif t == "chart":
            self.segments.append({"kind": "chart", "chart": ev})
        elif t == "table":
            self.segments.append({"kind": "table", "table": ev})
        elif t == "tool":
            if ev.get("status") == "running":
                self.tools.append({"name": ev["name"], "input": ev.get("input"), "done": False})
            else:
                for tool in reversed(self.tools):
                    if tool["name"] == ev["name"] and not tool["done"]:
                        tool["done"] = True
                        break

    def content(self, usage: dict) -> dict:
        return {"segments": self.segments, "tools": self.tools, "usage": usage}


@app.post("/chat")
async def chat(req: ChatRequest, user: AuthUser = Depends(get_current_user)):
    """Stream SSE del agente. Eventos: meta, token, tool, chart, table, done, error.
    Sin conversation_id crea la conversación; con él, la continúa (si es del usuario)."""
    if req.conversation_id:
        conv_id = _require_uuid(req.conversation_id)
        history = store.get_api_history(user.id, conv_id)
        if history is None:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
    else:
        conv_id = store.create_conversation(user.id, store.make_title(req.message))
        history = []
    full_history = list(history) + [{"role": "user", "content": req.message}]

    async def event_source():
        yield {"event": "meta", "data": json.dumps({"conversation_id": conv_id})}
        acc = _TurnAccumulator()
        async for ev in stream_agent(full_history):
            etype = ev.get("type")
            if etype == "done":
                try:
                    store.append_turn(user.id, conv_id, req.message,
                                      acc.content(ev.get("usage", {})), ev["messages"])
                except Exception as e:  # noqa: BLE001 — el chat respondió; avisar sin romper
                    yield {"event": "error",
                           "data": json.dumps({"type": "error",
                                               "message": f"Respuesta no persistida: {e}"})}
                yield {"event": "done",
                       "data": json.dumps({"conversation_id": conv_id,
                                           "usage": ev.get("usage", {})}, ensure_ascii=False)}
            else:
                acc.feed(ev)
                yield {"event": etype, "data": json.dumps(ev, ensure_ascii=False, default=str)}

    return EventSourceResponse(event_source())


# --- Conversaciones (persistencia por usuario) ------------------------------
@app.get("/conversations")
def conversations(user: AuthUser = Depends(get_current_user)) -> dict:
    return {"conversations": store.list_conversations(user.id)}


@app.get("/conversations/{conversation_id}")
def conversation_detail(conversation_id: str, user: AuthUser = Depends(get_current_user)) -> dict:
    msgs = store.get_messages(user.id, _require_uuid(conversation_id))
    if msgs is None:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return {"id": conversation_id, "messages": msgs}


@app.delete("/conversations/{conversation_id}")
def conversation_delete(conversation_id: str, user: AuthUser = Depends(get_current_user)) -> dict:
    if not store.delete_conversation(user.id, _require_uuid(conversation_id)):
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return {"status": "deleted", "id": conversation_id}


@app.patch("/conversations/{conversation_id}")
def conversation_rename(conversation_id: str, req: RenameRequest,
                        user: AuthUser = Depends(get_current_user)) -> dict:
    if not store.rename_conversation(user.id, _require_uuid(conversation_id), req.title):
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return {"status": "renamed", "id": conversation_id}


@app.post("/export/csv")
def export_csv(req: ExportRequest, user: AuthUser = Depends(get_current_user)):
    """Exporta una tabla (la que el frontend ya recibió por SSE) a CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(req.columns)
    writer.writerows(req.rows)
    fname = req.filename if req.filename.endswith(".csv") else f"{req.filename}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# --- Insights (Sistema de Insights Automáticos, 30%) -----------------------
_REPORT_CACHE: dict = {}


def _get_report(refresh: bool = False) -> dict:
    if refresh or "report" not in _REPORT_CACHE:
        _REPORT_CACHE["report"] = build_report()
    return _REPORT_CACHE["report"]


@app.get("/insights")
def insights(refresh: bool = False, user: AuthUser = Depends(get_current_user)) -> dict:
    """Reporte ejecutivo estructurado (JSON): resumen, top hallazgos, detalle por categoría, calidad."""
    return _get_report(refresh)


@app.get("/insights/markdown")
def insights_markdown(ai: bool = False, refresh: bool = False, user: AuthUser = Depends(get_current_user)):
    """Reporte ejecutivo en Markdown. ai=true antepone una síntesis redactada por Claude."""
    report = _get_report(refresh)
    md = to_markdown(report)
    if ai:
        prose = narrate(report)
        if prose:
            md = f"## Síntesis ejecutiva (IA)\n\n{prose}\n\n---\n\n{md}"
    return Response(content=md, media_type="text/markdown; charset=utf-8")


@app.get("/insights/narrative")
def insights_narrative(refresh: bool = False, user: AuthUser = Depends(get_current_user)) -> dict:
    """Síntesis ejecutiva redactada por Claude desde los hallazgos ya calculados.
    Devuelve available=false si no hay ANTHROPIC_API_KEY configurada."""
    text = narrate(_get_report(refresh))
    return {"text": text, "available": bool(text)}

