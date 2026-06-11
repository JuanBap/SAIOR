import Link from "next/link";
import {
  ArrowDown,
  ArrowRight,
  Database,
  FlaskConical,
  LayoutDashboard,
  ShieldCheck,
} from "lucide-react";

const BULLETS = [
  {
    icon: ShieldCheck,
    title: "Cero números inventados",
    text: "El LLM traduce y narra — jamás calcula. Cada cifra sale de una consulta real sobre los datos.",
  },
  {
    icon: Database,
    title: "Dos niveles de consulta",
    text: "Herramientas verificadas con tests de regresión + SQL generado con guardrails (read-only, AST, auditado).",
  },
  {
    icon: LayoutDashboard,
    title: "Insights con criterio de negocio",
    text: "Anomalías, tendencias y oportunidades priorizadas por impacto ponderado por volumen de órdenes.",
  },
  {
    icon: FlaskConical,
    title: "Precisión medida, no afirmada",
    text: "56 tests de regresión y una suite en vivo del agente respaldan cada respuesta.",
  },
] as const;

function DiagramBox({
  title,
  subtitle,
  accent = false,
}: {
  title: string;
  subtitle: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border px-4 py-2.5 text-center ${
        accent ? "border-rappi/40 bg-rappi/10" : "border-border bg-card/70"
      }`}
    >
      <p className={`text-[13px] font-semibold ${accent ? "text-rappi-soft" : ""}`}>{title}</p>
      <p className="text-[11px] text-muted-foreground">{subtitle}</p>
    </div>
  );
}

export default function Landing() {
  return (
    <div className="flex flex-1 items-center overflow-y-auto px-6 py-6 lg:h-[calc(100dvh-3.5rem)] lg:overflow-hidden">
      <div className="mx-auto grid w-full max-w-6xl items-center gap-10 lg:grid-cols-[1.1fr_1fr]">
        {/* Izquierda: pitch */}
        <div>
          <p className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-rappi/30 bg-rappi/10 px-3 py-1 text-[11px] font-medium text-rappi-soft">
            980 zonas · 9 países · 13 métricas · multiusuario con chats persistentes
          </p>
          <h1 className="text-3xl leading-tight font-semibold tracking-tight text-balance xl:text-[2.6rem] xl:leading-[1.15]">
            Pregúntale a tus operaciones.
            <br />
            <span className="text-rappi-soft">Respuestas que no alucinan.</span>
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted-foreground">
            SAIOR convierte preguntas en español en consultas deterministas sobre las métricas de
            Rappi, las visualiza al instante y genera insights ejecutivos automáticos.
          </p>

          <ul className="mt-5 space-y-3">
            {BULLETS.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex items-start gap-3">
                <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg bg-rappi/12 text-rappi-soft">
                  <Icon className="size-4" />
                </span>
                <p className="text-[13px] leading-snug">
                  <span className="font-semibold">{title}.</span>{" "}
                  <span className="text-muted-foreground">{text}</span>
                </p>
              </li>
            ))}
          </ul>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Link
              href="/chat"
              className="inline-flex items-center gap-1.5 rounded-xl bg-rappi px-5 py-2.5 text-sm font-medium text-white shadow-[0_0_24px_rgba(255,68,31,0.35)] transition-opacity hover:opacity-90"
            >
              Entrar al chat <ArrowRight className="size-4" />
            </Link>
            <Link
              href="/insights"
              className="inline-flex items-center gap-1.5 rounded-xl border px-5 py-2.5 text-sm text-foreground/90 transition-colors hover:bg-muted"
            >
              Ver insights automáticos
            </Link>
          </div>
          <p className="mt-4 text-[11px] text-muted-foreground/60">
            Next.js + FastAPI + Supabase + Claude Sonnet 4.6 · ~$0.02 por consulta
          </p>
        </div>

        {/* Derecha: arquitectura */}
        <div className="rounded-2xl border bg-card/40 p-5">
          <p className="mb-3 text-center text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            Cómo responde sin alucinar
          </p>
          <div className="space-y-1.5">
            <DiagramBox title="Tu pregunta" subtitle="lenguaje natural, con memoria por conversación" />
            <ArrowDown className="mx-auto size-3.5 text-muted-foreground/60" />
            <DiagramBox
              accent
              title="Agente (Claude · temperatura 0)"
              subtitle="traduce a consultas tipadas — lo único probabilístico"
            />
            <ArrowDown className="mx-auto size-3.5 text-muted-foreground/60" />
            <div className="grid grid-cols-2 gap-1.5">
              <DiagramBox title="8 consultas verificadas" subtitle="pandas · golden tests" />
              <DiagramBox title="SQL generado" subtitle="read-only · AST · auditado" />
            </div>
            <ArrowDown className="mx-auto size-3.5 text-muted-foreground/60" />
            <DiagramBox
              title="Supabase (Postgres)"
              subtitle="datos · auth · conversaciones · log de auditoría"
            />
            <ArrowDown className="mx-auto size-3.5 text-muted-foreground/60" />
            <DiagramBox
              accent
              title="Respuesta anclada"
              subtitle="narración + gráficos construidos desde el resultado real"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
