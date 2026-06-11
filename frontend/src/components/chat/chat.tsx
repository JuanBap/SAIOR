"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Plus, Send } from "lucide-react";

import {
  deleteConversation,
  getConversation,
  listConversations,
  streamChat,
  type Conversation,
  type StoredMessage,
} from "@/lib/api";
import type { Segment, Turn } from "@/components/chat/types";
import { Sidebar } from "@/components/chat/sidebar";
import { Suggestions } from "@/components/chat/suggestions";
import { TurnView } from "@/components/chat/turn";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Reconstruye los turnos de la UI desde los mensajes persistidos (replay fiel:
 *  los gráficos/tablas se re-renderizan desde el mismo JSON determinista). */
function storedToTurns(messages: StoredMessage[]): Turn[] {
  return messages.map((m) => {
    if (m.role === "user") {
      return {
        role: "user" as const,
        segments: [{ kind: "text" as const, text: m.content.text ?? "" }],
        tools: [],
      };
    }
    return {
      role: "assistant" as const,
      segments: (m.content.segments ?? []) as Segment[],
      tools: m.content.tools ?? [],
      usage: m.content.usage,
      tier: m.content.tier,
    };
  });
}

export function Chat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingConv, setLoadingConv] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const refreshList = useCallback(async () => {
    try {
      setConversations(await listConversations());
    } catch {
      /* el health dot del header ya avisa si el backend no está */
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    refreshList();
  }, [refreshList]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

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

  async function openConversation(id: string) {
    if (streaming || id === activeId) return;
    setLoadingConv(true);
    try {
      const detail = await getConversation(id);
      setTurns(storedToTurns(detail.messages));
      setActiveId(id);
    } catch {
      /* si falla, se mantiene la vista actual */
    } finally {
      setLoadingConv(false);
    }
  }

  function newConversation() {
    if (streaming) return;
    setTurns([]);
    setActiveId(null);
  }

  async function removeConversation(id: string) {
    if (!window.confirm("¿Eliminar esta conversación? No se puede deshacer.")) return;
    try {
      await deleteConversation(id);
      if (id === activeId) newConversation();
      refreshList();
    } catch {
      /* noop */
    }
  }

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
      for await (const ev of streamChat(message, activeId)) {
        if (ev.event === "meta") {
          setActiveId(ev.data.conversation_id);
        } else if (ev.event === "token") {
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
          const { usage, tier } = ev.data;
          patchLast((t) => ({ ...t, usage, tier, streaming: false }));
          refreshList();
        } else if (ev.event === "error") {
          const msg = ev.data.message;
          patchLast((t) => ({ ...t, error: msg, streaming: false }));
        }
      }
    } catch (e) {
      const msg =
        e instanceof Error && e.message.includes("sesión")
          ? e.message
          : "No se pudo conectar con el backend. Levántalo con: cd backend/src && uvicorn api:app --port 8000";
      patchLast((t) => ({ ...t, error: msg, streaming: false }));
    } finally {
      setStreaming(false);
      patchLast((t) => ({ ...t, streaming: false }));
    }
  }

  const empty = turns.length === 0;

  return (
    <div className="flex h-[calc(100dvh-3.5rem)]">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        loading={loadingList}
        onSelect={openConversation}
        onNew={newConversation}
        onDelete={removeConversation}
      />

      <div className="mx-auto flex h-full w-full max-w-3xl flex-col px-4">
        {loadingConv ? (
          <div className="grid flex-1 place-items-center text-muted-foreground">
            <span className="flex items-center gap-2 text-sm">
              <Loader2 className="size-4 animate-spin text-rappi-soft" /> Cargando conversación…
            </span>
          </div>
        ) : empty ? (
          <div className="flex flex-1 flex-col justify-center gap-8 overflow-y-auto py-10">
            <div className="text-center">
              <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                Pregúntale a tus datos de <span className="text-rappi-soft">operaciones</span>
              </h1>
              <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
                980 zonas · 9 países · 13 métricas · últimas 8 semanas. El agente traduce tu
                pregunta a consultas deterministas — cada número proviene del cálculo, no del
                modelo.
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
                onClick={newConversation}
                title="Nueva conversación"
              >
                <Plus />
              </Button>
            )}
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ej: ¿qué zonas problemáticas hay en Colombia?"
              disabled={streaming || loadingConv}
              className="h-10 flex-1 rounded-xl"
              autoFocus
            />
            <Button
              type="submit"
              disabled={streaming || loadingConv || !input.trim()}
              className="h-10 rounded-xl px-4"
            >
              <Send data-icon="inline-start" />
              Enviar
            </Button>
          </form>
          <p className="mt-2 text-center text-[11px] text-muted-foreground/60">
            Conversaciones guardadas por usuario · los gráficos y tablas se generan desde el
            resultado real de cada consulta
          </p>
        </div>
      </div>
    </div>
  );
}
