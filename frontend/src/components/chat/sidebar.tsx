"use client";

import { Loader2, MessageSquare, Plus, Trash2 } from "lucide-react";

import type { Conversation } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diff / 60_000);
  if (mins < 1) return "ahora";
  if (mins < 60) return `hace ${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.round(hours / 24);
  return days === 1 ? "ayer" : `hace ${days} días`;
}

export function Sidebar({
  conversations,
  activeId,
  loading,
  onSelect,
  onNew,
  onDelete,
}: {
  conversations: Conversation[];
  activeId: string | null;
  loading: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}) {
  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r bg-card/30 sm:flex">
      <div className="p-3">
        <Button size="sm" variant="outline" className="w-full" onClick={onNew}>
          <Plus data-icon="inline-start" />
          Nueva conversación
        </Button>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        {loading ? (
          <p className="flex items-center gap-2 px-2 py-3 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" /> Cargando…
          </p>
        ) : conversations.length === 0 ? (
          <p className="px-2 py-3 text-xs leading-relaxed text-muted-foreground">
            Sin conversaciones todavía. Pregunta algo y quedará guardada aquí.
          </p>
        ) : (
          conversations.map((c) => (
            <div
              key={c.id}
              className={cn(
                "group flex items-center gap-1 rounded-lg pr-1 transition-colors",
                c.id === activeId ? "bg-rappi/15" : "hover:bg-muted/60",
              )}
            >
              <button
                onClick={() => onSelect(c.id)}
                className="min-w-0 flex-1 px-2.5 py-2 text-left"
              >
                <span
                  className={cn(
                    "flex items-center gap-1.5 truncate text-[13px]",
                    c.id === activeId ? "font-medium text-foreground" : "text-foreground/80",
                  )}
                >
                  <MessageSquare className="size-3 shrink-0 opacity-50" />
                  <span className="truncate">{c.title}</span>
                </span>
                <span className="mt-0.5 block pl-[18px] text-[10px] text-muted-foreground">
                  {relTime(c.updated_at)}
                </span>
              </button>
              <button
                onClick={() => onDelete(c.id)}
                title="Eliminar conversación"
                className="grid size-6 shrink-0 place-items-center rounded-md text-muted-foreground opacity-0 transition-all group-hover:opacity-100 hover:bg-red-500/15 hover:text-red-300"
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))
        )}
      </nav>

      <p className="border-t px-3 py-2 text-[10px] leading-relaxed text-muted-foreground/70">
        Tus conversaciones se guardan por usuario y puedes continuarlas cuando quieras.
      </p>
    </aside>
  );
}
