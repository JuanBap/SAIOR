"use client";

import { Download } from "lucide-react";

import type { TableSpec } from "@/lib/api";
import { fmtValue } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardAction } from "@/components/ui/card";

function csvEscape(v: unknown): string {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function downloadCSV(table: TableSpec) {
  const lines = [
    table.columns.join(","),
    ...table.rows.map((r) => r.map(csvEscape).join(",")),
  ];
  const blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${table.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 60)}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function cell(col: string, v: string | number | null, format?: string): React.ReactNode {
  if (v === null || v === undefined) return <span className="text-muted-foreground">—</span>;
  if (col === "QUALITY_FLAG") {
    return v === "OK" ? (
      <span className="text-muted-foreground">OK</span>
    ) : (
      <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-400">
        {v}
      </span>
    );
  }
  if (typeof v === "number") {
    if (col === "VALUE" || col === "value" || col === "mean" || col === "median")
      return fmtValue(v, format);
    if (col === "GROWTH_PCT") return fmtValue(v, "percent_points");
    if (Number.isInteger(v)) return v.toLocaleString("es");
    return String(Number(v.toFixed(4)));
  }
  return String(v);
}

export function TableCard({ table }: { table: TableSpec }) {
  return (
    <Card className="my-3 gap-2 py-4">
      <CardHeader className="px-4">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {table.title} <span className="text-xs">· {table.rows.length} filas</span>
        </CardTitle>
        <CardAction>
          <Button size="xs" variant="outline" onClick={() => downloadCSV(table)}>
            <Download data-icon="inline-start" />
            CSV
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="px-4">
        <div className="max-h-80 overflow-auto rounded-lg border">
          <table className="w-full text-xs">
            <thead className="sticky top-0 z-10 bg-card">
              <tr className="border-b text-left text-muted-foreground">
                {table.columns.map((c) => (
                  <th key={c} className="px-2.5 py-2 font-medium whitespace-nowrap">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, i) => (
                <tr key={i} className="border-b border-border/50 last:border-0 hover:bg-muted/40">
                  {row.map((v, j) => (
                    <td key={j} className="px-2.5 py-1.5 whitespace-nowrap">
                      {cell(table.columns[j], v, table.meta?.format)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
