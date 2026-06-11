"use client";

import {
  ArrowLeftRight,
  Filter,
  Layers,
  Lightbulb,
  Sigma,
  TrendingUp,
} from "lucide-react";

/** Los 6 casos de uso obligatorios del brief, como tarjetas clickeables (demo en vivo). */
const SUGGESTIONS = [
  {
    tag: "Filtrado",
    icon: Filter,
    q: "¿Cuáles son las 5 zonas con mayor % Lead Penetration esta semana?",
  },
  {
    tag: "Comparación",
    icon: ArrowLeftRight,
    q: "Compara el Perfect Order entre zonas Wealthy y Non Wealthy en México",
  },
  {
    tag: "Tendencia",
    icon: TrendingUp,
    q: "Muestra la evolución de Gross Profit UE en Chapinero últimas 8 semanas",
  },
  {
    tag: "Agregación",
    icon: Sigma,
    q: "¿Cuál es el promedio de Lead Penetration por país?",
  },
  {
    tag: "Multivariable",
    icon: Layers,
    q: "¿Qué zonas tienen alto Lead Penetration pero bajo Perfect Order?",
  },
  {
    tag: "Inferencia",
    icon: Lightbulb,
    q: "¿Cuáles son las zonas que más crecen en órdenes en las últimas 5 semanas y qué podría explicar el crecimiento?",
  },
] as const;

export function Suggestions({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="grid gap-2.5 sm:grid-cols-2">
      {SUGGESTIONS.map(({ tag, icon: Icon, q }) => (
        <button
          key={tag}
          onClick={() => onPick(q)}
          className="group flex items-start gap-3 rounded-xl border bg-card/60 p-3.5 text-left transition-all hover:border-rappi/50 hover:bg-card"
        >
          <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-rappi/12 text-rappi-soft transition-colors group-hover:bg-rappi/20">
            <Icon className="size-4" />
          </span>
          <span>
            <span className="block text-[11px] font-medium tracking-wide text-rappi-soft uppercase">
              {tag}
            </span>
            <span className="mt-0.5 block text-[13px] leading-snug text-foreground/90">{q}</span>
          </span>
        </button>
      ))}
    </div>
  );
}
