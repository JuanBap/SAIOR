"use client";

import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";

import type { Segment, ToolCall, Turn } from "@/components/chat/types";
import { ChartCard } from "@/components/chat/chart-card";
import { Md } from "@/components/chat/markdown";
import { TableCard } from "@/components/chat/table-card";
import { Badge } from "@/components/ui/badge";
import { costUSD, totalInputTokens } from "@/lib/format";

/** Resumen compacto de los parámetros con que el agente llamó la herramienta. */
function toolParams(input?: Record<string, unknown>): string {
  if (!input) return "";
  const keys = [
    "metric",
    "metric_high",
    "metric_low",
    "dimension",
    "group_by",
    "text",
    "weeks",
    "top_n",
  ];
  const parts: string[] = [];
  for (const k of keys) {
    if (input[k] !== undefined) parts.push(String(input[k]));
  }
  const f = input.filters as Record<string, unknown> | undefined;
  if (f) for (const v of Object.values(f)) if (v) parts.push(String(v));
  return parts.slice(0, 4).join(" · ");
}

function ToolChips({ tools }: { tools: ToolCall[] }) {
  if (!tools.length) return null;
  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {tools.map((t, i) => (
        <Badge key={i} variant="outline" className="gap-1.5 font-mono text-[10px] text-muted-foreground">
          {t.done ? (
            <CheckCircle2 className="size-3 text-emerald-400" />
          ) : (
            <Loader2 className="size-3 animate-spin text-rappi-soft" />
          )}
          {t.name}
          {toolParams(t.input) && <span className="opacity-60">({toolParams(t.input)})</span>}
        </Badge>
      ))}
    </div>
  );
}

function SegmentView({ seg }: { seg: Segment }) {
  if (seg.kind === "text") return seg.text.trim() ? <Md>{seg.text}</Md> : null;
  if (seg.kind === "chart") return <ChartCard chart={seg.chart} />;
  return <TableCard table={seg.table} />;
}

export function TurnView({ turn }: { turn: Turn }) {
  if (turn.role === "user") {
    const text = turn.segments[0]?.kind === "text" ? turn.segments[0].text : "";
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-rappi/15 px-4 py-2.5 text-sm leading-relaxed text-foreground ring-1 ring-rappi/25 sm:max-w-[70%]">
          {text}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <span className="mt-1 grid size-7 shrink-0 place-items-center rounded-lg bg-rappi text-[11px] font-black text-white">
        R
      </span>
      <div className="min-w-0 flex-1">
        <ToolChips tools={turn.tools} />
        {turn.segments.map((seg, i) => (
          <SegmentView key={i} seg={seg} />
        ))}
        {turn.streaming && (
          <span className="ml-0.5 inline-block h-4 w-2 animate-pulse rounded-sm bg-rappi-soft align-text-bottom" />
        )}
        {turn.error && (
          <div className="mt-2 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            {turn.error}
          </div>
        )}
        {turn.usage && (
          <p className="mt-1.5 text-[11px] text-muted-foreground/70">
            claude-sonnet-4-6 · {totalInputTokens(turn.usage).toLocaleString("es")} in
            {(turn.usage.cache_read_input_tokens ?? 0) > 0 &&
              ` (${(turn.usage.cache_read_input_tokens ?? 0).toLocaleString("es")} caché)`}{" "}
            / {turn.usage.output_tokens.toLocaleString("es")} out tokens · ≈ $
            {costUSD(turn.usage).toFixed(4)} USD
          </p>
        )}
      </div>
    </div>
  );
}
