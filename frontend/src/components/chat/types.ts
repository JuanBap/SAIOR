import type { ChartSpec, TableSpec, Usage } from "@/lib/api";

export type Segment =
  | { kind: "text"; text: string }
  | { kind: "chart"; chart: ChartSpec }
  | { kind: "table"; table: TableSpec };

export type ToolCall = {
  name: string;
  input?: Record<string, unknown>;
  done: boolean;
};

export type Turn = {
  role: "user" | "assistant";
  segments: Segment[];
  tools: ToolCall[];
  usage?: Usage;
  error?: string;
  streaming?: boolean;
  tier?: string;
};
