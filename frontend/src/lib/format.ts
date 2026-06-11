/** Formateo de valores según el catálogo de métricas + utilidades de presentación. */

export function fmtValue(v: unknown, format?: string): string {
  if (v === null || v === undefined || (typeof v === "number" && !isFinite(v))) return "—";
  if (typeof v !== "number") return String(v);
  if (format === "percent") return `${(v * 100).toFixed(1)}%`;
  if (format === "percent_points") return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  if (format === "decimal_2") return v.toFixed(2);
  if (format === "integer") return Math.round(v).toLocaleString("es");
  if (Math.abs(v) >= 1000) return v.toLocaleString("es", { maximumFractionDigits: 0 });
  return String(Number(v.toFixed(4)));
}

/** Nombres cortos para ejes y heatmap (los nombres reales son larguísimos). */
export const METRIC_SHORT: Record<string, string> = {
  "Lead Penetration": "Lead Pen.",
  "Perfect Orders": "Perfect Orders",
  "Gross Profit UE": "GP UE",
  "Pro Adoption (Last Week Status)": "Pro Adoption",
  "% PRO Users Who Breakeven": "PRO Breakeven",
  "MLTV Top Verticals Adoption": "MLTV",
  "Non-Pro PTC > OP": "PTC→OP",
  "Restaurants SST > SS CVR": "Rest SST→SS",
  "Restaurants SS > ATC CVR": "Rest SS→ATC",
  "Retail SST > SS CVR": "Retail SST→SS",
  "% Restaurants Sessions With Optimal Assortment": "Optimal Assort.",
  "Restaurants Markdowns / GMV": "Markdowns/GMV",
  "Turbo Adoption": "Turbo",
  Orders: "Órdenes",
};

export function shortMetric(m: string): string {
  return METRIC_SHORT[m] ?? m;
}

/** Costo estimado por consulta — Claude Sonnet 4.6 ($/millón de tokens):
 *  input $3 · cache write $3.75 (1.25×) · cache read $0.30 (0.1×) · output $15. */
export function costUSD(u: {
  input_tokens: number;
  output_tokens: number;
  cache_read_input_tokens?: number;
  cache_creation_input_tokens?: number;
}): number {
  return (
    u.input_tokens * 3e-6 +
    (u.cache_creation_input_tokens ?? 0) * 3.75e-6 +
    (u.cache_read_input_tokens ?? 0) * 0.3e-6 +
    u.output_tokens * 15e-6
  );
}

/** Total de tokens de entrada (incluye los servidos desde caché). */
export function totalInputTokens(u: {
  input_tokens: number;
  cache_read_input_tokens?: number;
  cache_creation_input_tokens?: number;
}): number {
  return u.input_tokens + (u.cache_read_input_tokens ?? 0) + (u.cache_creation_input_tokens ?? 0);
}

/** Color del heatmap: score 0 (peor) → rojo, 1 (mejor) → verde. */
export function heatColor(score: number): string {
  const hue = Math.round(Math.max(0, Math.min(1, score)) * 120);
  return `hsl(${hue} 58% 37% / 0.92)`;
}

export const CATEGORY_LABELS: Record<string, string> = {
  anomaly: "Anomalías",
  trend: "Tendencias",
  benchmark: "Benchmarking",
  opportunity: "Oportunidades",
  correlation: "Correlaciones",
  quality: "Calidad",
};

export function findingLocation(f: {
  country: string | null;
  city: string | null;
  zone: string | null;
}): string {
  const parts = [f.city, f.zone].filter(Boolean);
  const base = parts.join(" / ") || "Portafolio";
  return f.country ? `${base} (${f.country})` : base;
}
