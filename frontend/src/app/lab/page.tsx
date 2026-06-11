"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  ChevronRight,
  Cpu,
  Database,
  FlaskConical,
  Loader2,
  RefreshCw,
  ScrollText,
  Wrench,
} from "lucide-react";

import { getLab, type LabData } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

function Stat({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <Card className="gap-1 py-4">
      <CardContent className="px-4">
        <p className={cn("text-2xl font-semibold tracking-tight", accent && "text-rappi-soft")}>
          {value}
        </p>
        <p className="text-xs text-muted-foreground">{label}</p>
        {sub && <p className="mt-0.5 text-[10px] text-muted-foreground/70">{sub}</p>}
      </CardContent>
    </Card>
  );
}

/** Barra horizontal proporcional — divs puros para que funcione igual en ambos temas. */
function HBar({ label, count, max }: { label: string; count: number; max: number }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-44 shrink-0 truncate font-mono text-[11px] text-muted-foreground">
        {label}
      </span>
      <div className="h-4 flex-1 overflow-hidden rounded bg-muted/60">
        <div
          className="h-full rounded bg-rappi/80"
          style={{ width: `${Math.max(4, (count / max) * 100)}%` }}
        />
      </div>
      <span className="w-8 text-right font-medium">{count}</span>
    </div>
  );
}

export default function LabPage() {
  const [data, setData] = useState<LabData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [promptOpen, setPromptOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getLab());
    } catch {
      setError("No se pudo cargar el Lab. Verifica que el backend esté arriba.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !data) {
    return (
      <div className="grid flex-1 place-items-center text-muted-foreground">
        <span className="flex items-center gap-2 text-sm">
          <Loader2 className="size-4 animate-spin text-rappi-soft" /> Cargando métricas…
        </span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="grid flex-1 place-items-center px-4">
        <div className="flex max-w-md items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-700 dark:text-red-200">
          <AlertTriangle className="mt-0.5 size-5 shrink-0" />
          <div>
            {error}
            <Button size="sm" variant="outline" className="mt-3" onClick={load}>
              <RefreshCw data-icon="inline-start" /> Reintentar
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const { system, usage, tiers, tools_freq, conversations, query_log, activity } = data;
  const maxTool = Math.max(1, ...tools_freq.map((t) => t.count));
  const maxActivity = Math.max(1, ...activity.map((a) => a.turns));
  const tierTotal = Math.max(1, tiers.verified + tiers.generated);

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 px-4 py-8">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <FlaskConical className="size-6 text-rappi-soft" />
            Lab <span className="text-rappi-soft">· observabilidad</span>
          </h1>
          <p className="mt-1 text-xs text-muted-foreground">
            Telemetría real del sistema, calculada desde lo persistido en Supabase — sobrevive
            reinicios del backend
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={load} disabled={loading}>
          {loading ? (
            <Loader2 data-icon="inline-start" className="animate-spin" />
          ) : (
            <RefreshCw data-icon="inline-start" />
          )}
          Actualizar
        </Button>
      </div>

      {/* Stats principales */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Turnos respondidos" value={usage.turns.toLocaleString("es")} />
        <Stat
          label="Costo acumulado"
          value={`$${usage.est_cost_usd.toFixed(4)}`}
          sub={`≈ $${usage.avg_cost_per_turn_usd.toFixed(4)} por turno`}
          accent
        />
        <Stat
          label="Tokens entrada / salida"
          value={`${((usage.input_tokens + usage.cache_read_tokens + usage.cache_creation_tokens) / 1000).toFixed(1)}k / ${(usage.output_tokens / 1000).toFixed(1)}k`}
        />
        <Stat
          label="Cache hit del prompt"
          value={`${usage.cache_hit_pct}%`}
          sub={`${(usage.cache_read_tokens / 1000).toFixed(1)}k tokens leídos a 0.1×`}
        />
        <Stat
          label="SQL nivel 2"
          value={`${query_log.ok} ok · ${query_log.rejected} ✗`}
          sub={query_log.avg_ms ? `${query_log.avg_ms} ms promedio` : undefined}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Tiers + herramientas */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Wrench className="size-4 text-rappi-soft" /> Routing del motor
            </CardTitle>
            <CardDescription>
              Qué nivel respondió cada turno y qué herramientas orquestó el agente
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="flex h-5 w-full overflow-hidden rounded-lg">
                <div
                  className="bg-emerald-500/70"
                  style={{ width: `${(tiers.verified / tierTotal) * 100}%` }}
                  title={`verificadas: ${tiers.verified}`}
                />
                <div
                  className="bg-amber-500/80"
                  style={{ width: `${(tiers.generated / tierTotal) * 100}%` }}
                  title={`SQL generado: ${tiers.generated}`}
                />
              </div>
              <p className="mt-1.5 text-[11px] text-muted-foreground">
                <span className="font-medium text-emerald-700 dark:text-emerald-300">
                  ✓ {tiers.verified} verificadas
                </span>{" "}
                ·{" "}
                <span className="font-medium text-amber-700 dark:text-amber-300">
                  🧪 {tiers.generated} con SQL generado
                </span>
              </p>
            </div>
            <div className="space-y-1.5">
              {tools_freq.map((t) => (
                <HBar key={t.name} label={t.name} count={t.count} max={maxTool} />
              ))}
              {tools_freq.length === 0 && (
                <p className="text-xs text-muted-foreground">Aún no hay llamadas registradas.</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Usuarios + actividad */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Database className="size-4 text-rappi-soft" /> Uso por usuario
            </CardTitle>
            <CardDescription>
              {conversations.total} conversaciones · {conversations.messages} mensajes persistidos
              en Supabase
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-1.5 font-medium">Usuario</th>
                  <th className="py-1.5 text-right font-medium">Conversaciones</th>
                  <th className="py-1.5 text-right font-medium">Preguntas</th>
                </tr>
              </thead>
              <tbody>
                {conversations.by_user.map((u) => (
                  <tr key={u.email} className="border-b border-border/50 last:border-0">
                    <td className="py-1.5">{u.email}</td>
                    <td className="py-1.5 text-right">{u.conversations}</td>
                    <td className="py-1.5 text-right font-medium">{u.turns}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div>
              <p className="mb-1.5 text-[11px] font-medium text-muted-foreground">
                Preguntas por día
              </p>
              <div className="flex h-16 items-end gap-1">
                {activity.map((a) => (
                  <div key={a.date} className="flex flex-1 flex-col items-center gap-0.5">
                    <div
                      className="w-full rounded-t bg-rappi/70"
                      style={{ height: `${(a.turns / maxActivity) * 100}%`, minHeight: 3 }}
                      title={`${a.date}: ${a.turns}`}
                    />
                    <span className="text-[9px] text-muted-foreground">{a.date.slice(5)}</span>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Query log */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Database className="size-4 text-rappi-soft" /> Auditoría del SQL generado
            (app.query_log)
          </CardTitle>
          <CardDescription>
            Todo intento del nivel 2 queda registrado — incluidos los rechazados por el validador
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="px-2 py-1.5 font-medium">Hora</th>
                  <th className="px-2 py-1.5 font-medium">Usuario</th>
                  <th className="px-2 py-1.5 font-medium">Estado</th>
                  <th className="px-2 py-1.5 font-medium">SQL / error</th>
                  <th className="px-2 py-1.5 text-right font-medium">Filas</th>
                  <th className="px-2 py-1.5 text-right font-medium">ms</th>
                </tr>
              </thead>
              <tbody>
                {query_log.recent.map((q, i) => (
                  <tr key={i} className="border-b border-border/50 align-top last:border-0">
                    <td className="px-2 py-1.5 whitespace-nowrap text-muted-foreground">
                      {new Date(q.at).toLocaleTimeString("es")}
                    </td>
                    <td className="px-2 py-1.5 whitespace-nowrap">{q.email}</td>
                    <td className="px-2 py-1.5">
                      {q.ok ? (
                        <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:text-emerald-300">
                          OK
                        </span>
                      ) : (
                        <span className="rounded bg-red-500/15 px-1.5 py-0.5 text-[10px] font-medium text-red-700 dark:text-red-300">
                          RECHAZADA
                        </span>
                      )}
                    </td>
                    <td className="max-w-[480px] px-2 py-1.5">
                      <p className="truncate font-mono text-[11px]" title={q.sql}>
                        {q.sql}
                      </p>
                      {q.error && (
                        <p className="mt-0.5 truncate text-[10px] text-red-600/80 dark:text-red-300/70" title={q.error}>
                          {q.error}
                        </p>
                      )}
                    </td>
                    <td className="px-2 py-1.5 text-right">{q.rows ?? "—"}</td>
                    <td className="px-2 py-1.5 text-right">{q.ms ?? "—"}</td>
                  </tr>
                ))}
                {query_log.recent.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-2 py-3 text-muted-foreground">
                      Aún no se ha usado el nivel 2.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* System prompt */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Cpu className="size-4 text-rappi-soft" /> Configuración del agente
          </CardTitle>
          <CardDescription className="flex flex-wrap gap-2 pt-1">
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">{system.model}</span>
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">temperature 0</span>
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">
              snapshot: {system.snapshot_source}
            </span>
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">
              run_sql: {system.run_sql_enabled ? "ON" : "OFF"}
            </span>
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">
              {system.tools.length} herramientas
            </span>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-1.5 sm:grid-cols-2">
            {system.tools.map((t) => (
              <div key={t.name} className="rounded-lg border bg-card/60 px-3 py-2">
                <p className="font-mono text-[11px] font-medium text-rappi-soft">{t.name}</p>
                <p className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground" title={t.description}>
                  {t.description}
                </p>
              </div>
            ))}
          </div>

          <button
            onClick={() => setPromptOpen((o) => !o)}
            className="flex items-center gap-1.5 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
            aria-expanded={promptOpen}
          >
            <ChevronRight className={cn("size-3.5 transition-transform", promptOpen && "rotate-90")} />
            <ScrollText className="size-3.5" />
            Ver system prompt completo · {system.prompt_chars.toLocaleString("es")} caracteres
            (se cachea: la 1ª pregunta lo escribe, las siguientes lo leen a 0.1×)
          </button>
          {promptOpen && (
            <pre className="max-h-[420px] overflow-auto rounded-lg border bg-muted/30 p-4 font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
              {system.prompt}
            </pre>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
