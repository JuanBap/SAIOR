"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  Loader2,
  Mail,
  Printer,
  RefreshCw,
  Send,
  Sparkles,
  TrendingUp,
} from "lucide-react";

import {
  downloadInsightsMarkdown,
  getInsights,
  getNarrative,
  sendInsightsEmail,
  type InsightsReport,
} from "@/lib/api";
import { Input } from "@/components/ui/input";
import { CategoryTables } from "@/components/insights/category-tables";
import { FindingCard } from "@/components/insights/finding-card";
import { Heatmap } from "@/components/insights/heatmap";
import { Md } from "@/components/chat/markdown";
import { useConfirm } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { downloadElementPdf } from "@/lib/pdf";

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <Card className="gap-1 py-4">
      <CardContent className="px-4">
        <p className={`text-2xl font-semibold tracking-tight ${accent ? "text-rappi-soft" : ""}`}>
          {value}
        </p>
        <p className="text-xs text-muted-foreground">{label}</p>
      </CardContent>
    </Card>
  );
}

export default function InsightsPage() {
  const [report, setReport] = useState<InsightsReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [narrative, setNarrative] = useState<string | null>(null);
  const [narrating, setNarrating] = useState(false);
  const [emailOpen, setEmailOpen] = useState(false);
  const [emailTo, setEmailTo] = useState("");
  const [emailState, setEmailState] = useState<"idle" | "sending" | "ok" | "error">("idle");
  const [emailMsg, setEmailMsg] = useState<string | null>(null);
  const [pdfBusy, setPdfBusy] = useState(false);
  const reportRef = useRef<HTMLDivElement>(null);
  const confirm = useConfirm();

  async function exportPdf() {
    const ok = await confirm({
      title: "Descargar reporte en PDF",
      message: "Se generará un PDF con el reporte de insights completo. ¿Continuar?",
      confirmText: "Sí, descargar",
      cancelText: "No",
    });
    if (!ok) return;
    setPdfBusy(true);
    try {
      await downloadElementPdf(reportRef.current, "insights-rappi.pdf");
    } finally {
      setPdfBusy(false);
    }
  }

  async function sendEmail(e: React.FormEvent) {
    e.preventDefault();
    setEmailState("sending");
    setEmailMsg(null);
    try {
      const r = await sendInsightsEmail(emailTo, !!narrative);
      if (r.sent) {
        setEmailState("ok");
        setEmailMsg(`Reporte enviado a ${r.to}`);
        setTimeout(() => setEmailOpen(false), 2500);
      } else {
        setEmailState("error");
        setEmailMsg(r.message ?? "No se pudo enviar.");
      }
    } catch {
      setEmailState("error");
      setEmailMsg("Error de conexión con el backend.");
    }
  }

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      setReport(await getInsights(refresh));
    } catch {
      setError(
        "No se pudo cargar el reporte. Levanta el backend: cd backend/src && uvicorn api:app --port 8000",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function generateNarrative() {
    setNarrating(true);
    try {
      const { text, available } = await getNarrative();
      setNarrative(
        available
          ? text
          : "_La síntesis con IA requiere `ANTHROPIC_API_KEY` en `backend/.env`._",
      );
    } catch {
      setNarrative("_Error generando la síntesis. Revisa el backend._");
    } finally {
      setNarrating(false);
    }
  }

  if (loading && !report) {
    return (
      <div className="grid flex-1 place-items-center text-muted-foreground">
        <span className="flex items-center gap-2 text-sm">
          <Loader2 className="size-4 animate-spin text-rappi-soft" />
          Ejecutando detectores sobre 980 zonas…
        </span>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="grid flex-1 place-items-center px-4">
        <div className="flex max-w-md items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          <AlertTriangle className="mt-0.5 size-5 shrink-0" />
          <div>
            {error}
            <Button size="sm" variant="outline" className="mt-3" onClick={() => load()}>
              <RefreshCw data-icon="inline-start" /> Reintentar
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const s = report.summary;

  return (
    <div ref={reportRef} className="mx-auto w-full max-w-6xl space-y-6 px-4 py-8">
      {/* Toolbar */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Insights <span className="text-rappi-soft">automáticos</span>
          </h1>
          <p className="mt-1 text-xs text-muted-foreground">
            Generado {new Date(report.generated_at).toLocaleString("es")} · detección estadística
            determinista, sin LLM en el cálculo
          </p>
        </div>
        <div data-no-pdf="true" className="flex flex-wrap gap-2 print:hidden">
          <Button size="sm" variant="outline" onClick={() => load(true)} disabled={loading}>
            {loading ? (
              <Loader2 data-icon="inline-start" className="animate-spin" />
            ) : (
              <RefreshCw data-icon="inline-start" />
            )}
            Actualizar
          </Button>
          <Button size="sm" variant="outline" onClick={downloadInsightsMarkdown}>
            <Download data-icon="inline-start" /> Markdown
          </Button>
          <Button size="sm" variant="outline" onClick={exportPdf} disabled={pdfBusy}>
            {pdfBusy ? (
              <Loader2 data-icon="inline-start" className="animate-spin" />
            ) : (
              <Printer data-icon="inline-start" />
            )}
            PDF
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setEmailOpen((o) => !o);
              setEmailState("idle");
              setEmailMsg(null);
            }}
          >
            <Mail data-icon="inline-start" /> Email
          </Button>
          <Button size="sm" onClick={generateNarrative} disabled={narrating}>
            {narrating ? (
              <Loader2 data-icon="inline-start" className="animate-spin" />
            ) : (
              <Sparkles data-icon="inline-start" />
            )}
            Síntesis IA
          </Button>
        </div>
      </div>

      {/* Mini-formulario de email */}
      {emailOpen && (
        <form
          onSubmit={sendEmail}
          data-no-pdf="true"
          className="flex flex-wrap items-center gap-2 rounded-xl border bg-card/60 p-3 print:hidden"
        >
          <Mail className="size-4 text-rappi-soft" />
          <Input
            type="email"
            required
            placeholder="destinatario@empresa.com"
            value={emailTo}
            onChange={(e) => setEmailTo(e.target.value)}
            className="h-9 w-64"
            autoFocus
          />
          <Button type="submit" size="sm" disabled={emailState === "sending"}>
            {emailState === "sending" ? (
              <Loader2 data-icon="inline-start" className="animate-spin" />
            ) : (
              <Send data-icon="inline-start" />
            )}
            Enviar reporte{narrative ? " + síntesis IA" : ""}
          </Button>
          {emailMsg && (
            <span
              className={`flex items-center gap-1.5 text-xs ${
                emailState === "ok"
                  ? "text-emerald-600 dark:text-emerald-300"
                  : "text-amber-700 dark:text-amber-300"
              }`}
            >
              {emailState === "ok" && <CheckCircle2 className="size-3.5" />}
              {emailMsg}
            </span>
          )}
        </form>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Hallazgos detectados" value={s.total_findings.toLocaleString("es")} />
        <Stat label="Severidad alta" value={s.high_severity.toLocaleString("es")} accent />
        <Stat label="Zonas analizadas" value={report.coverage.zones.toLocaleString("es")} />
        <Stat label="Países · semanas" value={`${report.coverage.countries.length} · 8`} />
      </div>

      {/* Síntesis IA */}
      {narrative && (
        <Card className="border-rappi/30 bg-rappi/5">
          <CardContent className="px-5 py-1">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-rappi-soft uppercase">
              <Sparkles className="size-3.5" /> Síntesis ejecutiva (IA — redactada desde los números
              calculados)
            </p>
            <Md>{narrative}</Md>
          </CardContent>
        </Card>
      )}

      {/* Top hallazgos */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">
          Hallazgos críticos{" "}
          <span className="text-sm font-normal text-muted-foreground">
            — priorizados por impacto ponderado por volumen de órdenes
          </span>
        </h2>
        <div className="space-y-2.5">
          {report.top_findings.map((f, i) => (
            <FindingCard key={i} finding={f} index={i + 1} />
          ))}
        </div>
      </section>

      {/* Señales positivas */}
      {report.positive_signals.length > 0 && (
        <section className="space-y-2">
          <h2 className="flex items-center gap-1.5 text-sm font-semibold text-emerald-700 dark:text-emerald-300">
            <TrendingUp className="size-4" /> Señales positivas
          </h2>
          <div className="grid gap-2 sm:grid-cols-3">
            {report.positive_signals.map((f, i) => (
              <div
                key={i}
                className="rounded-lg border border-emerald-500/25 bg-emerald-500/8 p-3 text-xs"
              >
                <p className="font-medium">{f.metric}</p>
                <p className="mt-0.5 text-muted-foreground">
                  {[f.city, f.zone].filter(Boolean).join(" / ")} ({f.country})
                </p>
                <p className="mt-1 font-mono text-[11px] text-emerald-700/90 dark:text-emerald-200/90">{f.evidence}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Heatmap */}
      <Heatmap data={report.heatmap} />

      {/* Calidad de datos */}
      {report.quality.length > 0 && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm">
          <AlertTriangle className="mt-0.5 size-5 shrink-0 text-amber-400" />
          <div>
            <p className="font-medium text-amber-800 dark:text-amber-200">Calidad de datos</p>
            {report.quality.map((f, i) => (
              <p key={i} className="mt-1 text-[13px] text-amber-800/80 dark:text-amber-100/80">
                <span className="font-medium">{f.metric}:</span> {f.evidence}
              </p>
            ))}
            <p className="mt-1.5 text-[12px] text-amber-700/70 dark:text-amber-200/60 italic">
              {report.quality[0]?.recommendation}
            </p>
          </div>
        </div>
      )}

      {/* Detalle por categoría */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">Detalle por categoría</h2>
        <CategoryTables byCategory={report.by_category} counts={s.by_category} />
      </section>

      {/* Metodología */}
      <Card className="py-4">
        <CardContent className="px-5 text-[12px] leading-relaxed text-muted-foreground">
          <p className="mb-1 font-semibold text-foreground/80">Metodología</p>
          <p>
            Ranking: <code className="rounded bg-muted px-1">{report.methodology.impact_formula}</code>
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {report.methodology.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
            <li>
              Umbrales: anomalía ±{report.methodology.thresholds.anomaly_wow_pct}% WoW · tendencia{" "}
              {report.methodology.thresholds.trend_min_weeks}+ semanas · benchmark{" "}
              {report.methodology.thresholds.benchmark_sigma}σ · correlación |ρ|≥
              {report.methodology.thresholds.correlation_min_rho}.
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
