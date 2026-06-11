"use client";

import { useEffect, useRef, useState } from "react";
import { Plus, Send } from "lucide-react";

import { streamChat, type Usage } from "@/lib/api";
import type { Segment, Turn } from "@/components/chat/types";
import { Suggestions } from "@/components/chat/suggestions";
import { TurnView } from "@/components/chat/turn";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function Chat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  /** Muta el último turno (el del asistente en curso) de forma inmutable. */
  const patchLast = (fn: (t: Turn) => Turn) =>
    setTurns((prev) => {
      const next = [...prev];
      next[next.length - 1] = fn(next[next.length - 1]);
      return next;
    });

  const pushSegment = (seg: Segment) =>
    patchLast((t) => ({ ...t, segments: [...t.segments, seg] }));

  const appendToken = (text: string) =>
    patchLast((t) => {
      const segs = [...t.segments];
      const last = segs[segs.length - 1];
      if (last?.kind === "text") segs[segs.length - 1] = { ...last, text: last.text + text };
      else segs.push({ kind: "text", text });
      return { ...t, segments: segs };
    });

  async function send(text: string) {
    const message = text.trim();
    if (!message || streaming) return;
    setInput("");
    setStreaming(true);
    setTurns((prev) => [
      ...prev,
      { role: "user", segments: [{ kind: "text", text: message }], tools: [] },
      { role: "assistant", segments: [], tools: [], streaming: true },
    ]);

    try {
      for await (const ev of streamChat(message, sessionId)) {
        if (ev.event === "token") {
          appendToken(ev.data.text);
        } else if (ev.event === "tool") {
          const { name, input: toolInput, status } = ev.data;
          patchLast((t) => {
            const tools = [...t.tools];
            if (status === "running") tools.push({ name, input: toolInput, done: false });
            else {
              const idx = tools.findLastIndex((x) => x.name === name && !x.done);
              if (idx >= 0) tools[idx] = { ...tools[idx], done: true };
            }
            return { ...t, tools };
          });
        } else if (ev.event === "chart") {
          pushSegment({ kind: "chart", chart: ev.data });
        } else if (ev.event === "table") {
          pushSegment({ kind: "table", table: ev.data });
        } else if (ev.event === "done") {
          setSessionId(ev.data.session_id);
          const usage: Usage = ev.data.usage;
          patchLast((t) => ({ ...t, usage, streaming: false }));
        } else if (ev.event === "error") {
          const msg = ev.data.message;
          patchLast((t) => ({ ...t, error: msg, streaming: false }));
        }
      }
    } catch {
      patchLast((t) => ({
        ...t,
        error:
          "No se pudo conectar con el backend. Levántalo con: cd backend/src && uvicorn api:app --port 8000",
        streaming: false,
      }));
    } finally {
      setStreaming(false);
      patchLast((t) => ({ ...t, streaming: false }));
    }
  }

  function reset() {
    setTurns([]);
    setSessionId(null);
  }

  const empty = turns.length === 0;

  return (
    <div className="mx-auto flex h-[calc(100dvh-3.5rem)] w-full max-w-3xl flex-col px-4">
      {empty ? (
        <div className="flex flex-1 flex-col justify-center gap-8 py-10">
          <div className="text-center">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              Pregúntale a tus datos de <span className="text-rappi-soft">operaciones</span>
            </h1>
            <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
              980 zonas · 9 países · 13 métricas · últimas 8 semanas. El agente traduce tu pregunta
              a consultas deterministas — cada número proviene del cálculo, no del modelo.
            </p>
          </div>
          <Suggestions onPick={send} />
        </div>
      ) : (
        <div className="flex-1 space-y-6 overflow-y-auto py-6">
          {turns.map((t, i) => (
            <TurnView key={i} turn={t} />
          ))}
          <div ref={bottomRef} />
        </div>
      )}

      <div className="sticky bottom-0 z-10 bg-background/85 pt-2 pb-4 backdrop-blur-md">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="flex items-center gap-2"
        >
          {!empty && (
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={reset}
              title="Nueva conversación"
            >
              <Plus />
            </Button>
          )}
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ej: ¿qué zonas problemáticas hay en Colombia?"
            disabled={streaming}
            className="h-10 flex-1 rounded-xl"
            autoFocus
          />
          <Button
            type="submit"
            disabled={streaming || !input.trim()}
            className="h-10 rounded-xl px-4"
          >
            <Send data-icon="inline-start" />
            Enviar
          </Button>
        </form>
        <p className="mt-2 text-center text-[11px] text-muted-foreground/60">
          Memoria conversacional activa · los gráficos y tablas se generan desde el resultado real
          de cada consulta
        </p>
      </div>
    </div>
  );
}
