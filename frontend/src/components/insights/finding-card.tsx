"use client";

import type { Finding } from "@/lib/api";
import { findingLocation } from "@/lib/format";
import { cn } from "@/lib/utils";

const SEVERITY: Record<string, { label: string; cls: string; border: string }> = {
  high: { label: "ALTA", cls: "bg-red-500/15 text-red-300", border: "border-l-red-500/70" },
  medium: { label: "MEDIA", cls: "bg-amber-500/15 text-amber-300", border: "border-l-amber-500/70" },
  low: { label: "BAJA", cls: "bg-muted text-muted-foreground", border: "border-l-zinc-600" },
};

export function FindingCard({ finding, index }: { finding: Finding; index: number }) {
  const sev = SEVERITY[finding.severity] ?? SEVERITY.low;
  return (
    <div
      className={cn(
        "rounded-xl border border-l-4 bg-card/70 p-4 transition-colors hover:bg-card",
        sev.border,
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-muted-foreground">#{index}</span>
        <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wide", sev.cls)}>
          {sev.label}
        </span>
        <span className="text-sm font-semibold">{finding.metric}</span>
        <span className="text-sm text-muted-foreground">· {findingLocation(finding)}</span>
        <span className="ml-auto text-right text-[11px] text-muted-foreground">
          {finding.orders > 0 && (
            <span className="font-medium text-foreground/80">
              {finding.orders.toLocaleString("es")} órdenes ·{" "}
            </span>
          )}
          impacto {finding.impact_score.toLocaleString("es")}
        </span>
      </div>
      <p className="mt-2 font-mono text-[12.5px] text-foreground/85">{finding.evidence}</p>
      <p className="mt-1.5 text-[12.5px] text-muted-foreground italic">
        ↳ {finding.recommendation}
      </p>
    </div>
  );
}
