"use client";

import { useState } from "react";
import { ChevronRight, Download } from "lucide-react";

import type { TableSpec } from "@/lib/api";
import { fmtValue } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

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
      <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-400">
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

/** Colapsada por defecto: el gráfico cuenta la historia; la tabla es el detalle
 *  bajo demanda (y la vía de export CSV). Evita el muro de widgets por respuesta. */
export function TableCard({ table }: { table: TableSpec }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="my-2 rounded-xl border bg-card/60">
      <div className="flex items-center gap-2 px-3 py-2">
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex min-w-0 flex-1 items-center gap-1.5 text-left text-[13px] text-muted-foreground transition-colors hover:text-foreground"
          aria-expanded={open}
        >
          <ChevronRight
            className={cn("size-3.5 shrink-0 transition-transform", open && "rotate-90")}
          />
          <span className="truncate">
            {open ? table.title : `Ver datos — ${table.title}`}
          </span>
          <span className="shrink-0 text-[11px] opacity-70">· {table.rows.length} filas</span>
        </button>
        <Button size="xs" variant="ghost" onClick={() => downloadCSV(table)} title="Exportar CSV">
          <Download data-icon="inline-start" />
          CSV
        </Button>
      </div>

      {open && table.sql && (
        <pre className="overflow-x-auto border-t bg-muted/30 px-3 py-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-amber-700 dark:text-amber-200/80">
          {table.sql}
        </pre>
      )}
      {open && (
        <div className="max-h-80 overflow-auto border-t">
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
      )}
    </div>
  );
}
