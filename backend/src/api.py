"""API FastAPI — Sistema de Análisis Inteligente Rappi.

Expone el agente conversacional vía streaming SSE y utilidades de exportación.
La memoria conversacional se guarda por session_id en memoria (dict). Para una
demo/local no necesita persistencia; en producción se reemplazaría por Redis.

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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))
load_dotenv(SRC.parent / ".env")  # backend/.env

import os  # noqa: E402  (después de load_dotenv para que ANTHROPIC_MODEL ya esté disponible)

from agent import stream_agent  # noqa: E402

app = FastAPI(title="Rappi Insights API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Memoria conversacional en proceso: session_id -> lista de mensajes (incluye tool_use/result).
SESSIONS: dict[str, list[dict]] = {}


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None


class ExportRequest(BaseModel):
    columns: list[str]
    rows: list[list]
    filename: str = "export.csv"


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            "sessions": len(SESSIONS)}


@app.post("/chat")
async def chat(req: ChatRequest):
    """Stream SSE del agente. Eventos: token, tool, chart, table, done, error.
    El frontend lo consume con fetch + ReadableStream (POST, no EventSource nativo)."""
    session_id = req.session_id or uuid.uuid4().hex
    history = SESSIONS.get(session_id, []) + [{"role": "user", "content": req.message}]

    async def event_source():
        async for ev in stream_agent(history):
            etype = ev.get("type")
            if etype == "done":
                SESSIONS[session_id] = ev["messages"]  # persistir memoria del lado servidor
                yield {
                    "event": "done",
                    "data": json.dumps(
                        {"session_id": session_id, "usage": ev.get("usage", {})},
                        ensure_ascii=False,
                    ),
                }
            else:
                yield {"event": etype, "data": json.dumps(ev, ensure_ascii=False, default=str)}

    return EventSourceResponse(event_source())


@app.post("/export/csv")
def export_csv(req: ExportRequest):
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


@app.delete("/session/{session_id}")
def reset_session(session_id: str) -> dict:
    SESSIONS.pop(session_id, None)
    return {"status": "cleared", "session_id": session_id}
