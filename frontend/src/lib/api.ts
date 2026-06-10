/** Cliente del backend FastAPI: tipos compartidos + parser SSE del /chat. */

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------- tipos chat
export type ChartSpec = {
  type: "chart";
  kind: "line" | "bar" | "scatter";
  title: string;
  xKey: string;
  yKey: string;
  data: Record<string, string | number | null>[];
  meta?: { format?: string; higher_is_better?: boolean; spearman?: number };
};

export type TableSpec = {
  type: "table";
  title: string;
  columns: string[];
  rows: (string | number | null)[][];
  meta?: { format?: string };
};

export type ToolEvent = {
  type: "tool";
  name: string;
  input?: Record<string, unknown>;
  status: "running" | "done";
};

export type Usage = {
  input_tokens: number;
  output_tokens: number;
  cache_read_input_tokens?: number;
  cache_creation_input_tokens?: number;
};

export type SSEvent =
  | { event: "token"; data: { text: string } }
  | { event: "tool"; data: ToolEvent }
  | { event: "chart"; data: ChartSpec }
  | { event: "table"; data: TableSpec }
  | { event: "done"; data: { session_id: string; usage: Usage } }
  | { event: "error"; data: { message: string } };

// ------------------------------------------------------------- tipos insights
export type Finding = {
  category: string;
  scope: string;
  metric: string;
  direction: string | null;
  country: string | null;
  city: string | null;
  zone: string | null;
  zone_type: string | null;
  prioritization: string | null;
  orders: number;
  points: number;
  impact_score: number;
  severity: "high" | "medium" | "low";
  evidence: string;
  recommendation: string;
  [k: string]: unknown;
};

export type HeatmapData = {
  metrics: string[];
  countries: string[];
  cells: { metric: string; country: string; value: number; score: number }[];
  formats: Record<string, string>;
};

export type InsightsReport = {
  generated_at: string;
  summary: {
    total_findings: number;
    high_severity: number;
    by_category: Record<string, number>;
  };
  top_findings: Finding[];
  positive_signals: Finding[];
  by_category: Record<string, Finding[]>;
  heatmap: HeatmapData;
  quality: Finding[];
  coverage: { zones: number; countries: string[]; weeks: string };
  methodology: {
    impact_formula: string;
    thresholds: Record<string, number>;
    notes: string[];
  };
};

// ------------------------------------------------------------------ fetchers
export async function getHealth(): Promise<boolean> {
  try {
    const r = await fetch(`${API}/health`, { cache: "no-store" });
    return r.ok;
  } catch {
    return false;
  }
}

export async function getInsights(refresh = false): Promise<InsightsReport> {
  const r = await fetch(`${API}/insights${refresh ? "?refresh=true" : ""}`, {
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function getNarrative(): Promise<{ text: string; available: boolean }> {
  const r = await fetch(`${API}/insights/narrative`, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function downloadInsightsMarkdown(): Promise<void> {
  const r = await fetch(`${API}/insights/markdown`, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const blob = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "insights-rappi.md";
  a.click();
  URL.revokeObjectURL(a.href);
}

// ------------------------------------------------------------------ SSE /chat
/** El backend responde a POST /chat con SSE; EventSource nativo no soporta POST,
 *  así que parseamos el stream a mano (separador de eventos: línea en blanco). */
export async function* streamChat(
  message: string,
  sessionId?: string | null,
): AsyncGenerator<SSEvent> {
  const res = await fetch(`${API}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId ?? undefined }),
  });
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  const DELIM = /\r?\n\r?\n/;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let m: RegExpMatchArray | null;
    while ((m = buf.match(DELIM)) && m.index !== undefined) {
      const raw = buf.slice(0, m.index);
      buf = buf.slice(m.index + m[0].length);
      const ev = parseSSE(raw);
      if (ev) yield ev;
    }
  }
}

function parseSSE(raw: string): SSEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split(/\r?\n/)) {
    if (line.startsWith(":")) continue; // keepalive de sse-starlette
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) } as SSEvent;
  } catch {
    return null;
  }
}
