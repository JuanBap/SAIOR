"use client";

import type { HeatmapData } from "@/lib/api";
import { fmtValue, heatColor, shortMetric } from "@/lib/format";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function Heatmap({ data }: { data: HeatmapData }) {
  const byKey = new Map(data.cells.map((c) => [`${c.country}|${c.metric}`, c]));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Benchmarking país × métrica</CardTitle>
        <CardDescription>
          Promedio por país (semana actual). Color normalizado por métrica respetando su dirección:
          <span className="ml-1 inline-flex items-center gap-1">
            <span className="heat-cell inline-block size-2.5 rounded-sm" style={{ background: heatColor(0) }} />
            peor
            <span className="mx-0.5">→</span>
            <span className="heat-cell inline-block size-2.5 rounded-sm" style={{ background: heatColor(1) }} />
            mejor
          </span>
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-1">
            <thead>
              <tr>
                <th className="sticky left-0 bg-card text-left text-[11px] font-medium text-muted-foreground" />
                {data.metrics.map((m) => (
                  <th
                    key={m}
                    title={m}
                    className="min-w-[68px] px-1 pb-1 text-center text-[10px] font-medium text-muted-foreground"
                  >
                    {shortMetric(m)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.countries.map((country) => (
                <tr key={country}>
                  <td className="sticky left-0 bg-card pr-2 text-xs font-semibold text-foreground/90">
                    {country}
                  </td>
                  {data.metrics.map((metric) => {
                    const cell = byKey.get(`${country}|${metric}`);
                    if (!cell)
                      return (
                        <td
                          key={metric}
                          className="rounded-md bg-muted/40 py-1.5 text-center text-[10px] text-muted-foreground"
                          title={`${country} · ${metric}: sin datos`}
                        >
                          —
                        </td>
                      );
                    return (
                      <td
                        key={metric}
                        className="heat-cell rounded-md py-1.5 text-center text-[10px] font-medium text-white/95"
                        style={{ background: heatColor(cell.score) }}
                        title={`${country} · ${metric}: ${fmtValue(cell.value, data.formats[metric])}`}
                      >
                        {fmtValue(cell.value, data.formats[metric])}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
