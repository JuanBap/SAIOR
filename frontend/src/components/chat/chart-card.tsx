"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChartSpec } from "@/lib/api";
import { fmtValue, shortMetric } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const RAPPI = "#ff441f";
const GRID = "rgba(255,255,255,0.07)";
const AXIS = { fill: "#a1a1aa", fontSize: 11 } as const;
const TOOLTIP_STYLE = {
  backgroundColor: "#1c1c1f",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 8,
  fontSize: 12,
} as const;

function truncate(s: unknown, n = 22): string {
  const str = String(s ?? "");
  return str.length > n ? `${str.slice(0, n - 1)}…` : str;
}

export function ChartCard({ chart }: { chart: ChartSpec }) {
  const { kind, data, xKey, yKey, meta } = chart;
  const fmt = (v: unknown) => fmtValue(typeof v === "number" ? v : Number(v), meta?.format);

  let body: React.ReactNode = null;
  let height = 270;

  if (kind === "line") {
    body = (
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis
          dataKey={xKey}
          tick={AXIS}
          tickLine={false}
          axisLine={{ stroke: GRID }}
          tickFormatter={(w) => `S${w}`}
        />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={fmt} width={56} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          labelFormatter={(w) => `Semana ${w} (0 = actual)`}
          formatter={(v) => [fmt(v), chart.title]}
        />
        <Line
          type="monotone"
          dataKey={yKey}
          stroke={RAPPI}
          strokeWidth={2.5}
          dot={{ r: 3, fill: RAPPI, strokeWidth: 0 }}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    );
  } else if (kind === "bar") {
    const horizontal = data.length > 6 || data.some((d) => String(d[xKey] ?? "").length > 10);
    if (horizontal) {
      height = Math.min(460, Math.max(220, data.length * 34 + 60));
      body = (
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 18, bottom: 4, left: 4 }}>
          <CartesianGrid stroke={GRID} horizontal={false} />
          <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} tickFormatter={fmt} />
          <YAxis
            type="category"
            dataKey={xKey}
            tick={AXIS}
            tickLine={false}
            axisLine={false}
            width={150}
            tickFormatter={(v) => truncate(v, 20)}
          />
          <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [fmt(v), yKey]} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
          <Bar dataKey={yKey} fill={RAPPI} radius={[0, 4, 4, 0]} maxBarSize={22} />
        </BarChart>
      );
    } else {
      body = (
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={fmt} width={56} />
          <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [fmt(v), yKey]} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
          <Bar dataKey={yKey} fill={RAPPI} radius={[4, 4, 0, 0]} maxBarSize={48} />
        </BarChart>
      );
    }
  } else if (kind === "scatter") {
    height = 300;
    body = (
      <ScatterChart margin={{ top: 8, right: 16, bottom: 14, left: 8 }}>
        <CartesianGrid stroke={GRID} />
        <XAxis
          type="number"
          dataKey={xKey}
          name={shortMetric(xKey)}
          tick={AXIS}
          tickLine={false}
          axisLine={{ stroke: GRID }}
          label={{ value: shortMetric(xKey), position: "insideBottom", offset: -8, fill: "#71717a", fontSize: 11 }}
        />
        <YAxis
          type="number"
          dataKey={yKey}
          name={shortMetric(yKey)}
          tick={AXIS}
          tickLine={false}
          axisLine={false}
          width={56}
          label={{ value: shortMetric(yKey), angle: -90, position: "insideLeft", fill: "#71717a", fontSize: 11 }}
        />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          cursor={{ strokeDasharray: "4 4", stroke: "rgba(255,255,255,0.2)" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const p = payload[0].payload as Record<string, unknown>;
            return (
              <div style={TOOLTIP_STYLE} className="px-3 py-2">
                <p className="font-medium">{String(p.ZONE ?? "")}</p>
                <p className="text-muted-foreground">
                  {shortMetric(xKey)}: {fmtValue(Number(p[xKey]))} · {shortMetric(yKey)}:{" "}
                  {fmtValue(Number(p[yKey]))}
                </p>
              </div>
            );
          }}
        />
        <Scatter data={data} fill={RAPPI} fillOpacity={0.85} />
      </ScatterChart>
    );
  }

  return (
    <Card className="my-3 gap-2 py-4">
      <CardHeader className="px-4">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {chart.title}
          {meta?.spearman !== undefined && (
            <span className="ml-2 text-xs">· ρ Spearman {meta.spearman}</span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-2">
        <ResponsiveContainer width="100%" height={height}>
          {body as React.ReactElement}
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
