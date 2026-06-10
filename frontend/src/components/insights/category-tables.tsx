"use client";

import type { Finding } from "@/lib/api";
import { CATEGORY_LABELS, findingLocation } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const ZONE_CATS = ["anomaly", "trend", "benchmark", "opportunity"] as const;

function ZoneTable({ items }: { items: Finding[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="px-2.5 py-2 font-medium">Zona</th>
            <th className="px-2.5 py-2 font-medium">Métrica</th>
            <th className="px-2.5 py-2 font-medium">Evidencia</th>
            <th className="px-2.5 py-2 text-right font-medium">Órdenes</th>
            <th className="px-2.5 py-2 text-right font-medium">Impacto</th>
          </tr>
        </thead>
        <tbody>
          {items.map((f, i) => (
            <tr key={i} className="border-b border-border/50 last:border-0 hover:bg-muted/40">
              <td className="px-2.5 py-2 whitespace-nowrap">{findingLocation(f)}</td>
              <td className="px-2.5 py-2 whitespace-nowrap">{f.metric}</td>
              <td className="px-2.5 py-2 font-mono text-[11px]">{f.evidence}</td>
              <td className="px-2.5 py-2 text-right">{f.orders.toLocaleString("es")}</td>
              <td className="px-2.5 py-2 text-right font-medium">
                {f.impact_score.toLocaleString("es")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CorrelationTable({ items }: { items: Finding[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="px-2.5 py-2 font-medium">Relación</th>
            <th className="px-2.5 py-2 text-right font-medium">ρ Spearman</th>
            <th className="px-2.5 py-2 text-right font-medium">n zonas</th>
          </tr>
        </thead>
        <tbody>
          {items.map((f, i) => (
            <tr key={i} className="border-b border-border/50 last:border-0 hover:bg-muted/40">
              <td className="px-2.5 py-2">
                {String(f.metric_a)} <span className="text-muted-foreground">↔</span>{" "}
                {String(f.metric_b)}
              </td>
              <td className="px-2.5 py-2 text-right font-mono">
                {Number(f.rho) > 0 ? "+" : ""}
                {Number(f.rho).toFixed(2)}
              </td>
              <td className="px-2.5 py-2 text-right">{String(f.n)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CategoryTables({
  byCategory,
  counts,
}: {
  byCategory: Record<string, Finding[]>;
  counts: Record<string, number>;
}) {
  return (
    <Tabs defaultValue="anomaly">
      <TabsList>
        {[...ZONE_CATS, "correlation"].map((cat) => (
          <TabsTrigger key={cat} value={cat} className="text-xs">
            {CATEGORY_LABELS[cat]}
            <span className="ml-1 text-[10px] text-muted-foreground">{counts[cat] ?? 0}</span>
          </TabsTrigger>
        ))}
      </TabsList>
      {ZONE_CATS.map((cat) => (
        <TabsContent key={cat} value={cat}>
          <Card className="py-2">
            <CardContent className="px-2">
              <ZoneTable items={byCategory[cat] ?? []} />
              <p className="px-2.5 pt-2 pb-1 text-[11px] text-muted-foreground italic">
                {byCategory[cat]?.[0]?.recommendation}
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      ))}
      <TabsContent value="correlation">
        <Card className="py-2">
          <CardContent className="px-2">
            <CorrelationTable items={byCategory.correlation ?? []} />
            <p className="px-2.5 pt-2 pb-1 text-[11px] text-muted-foreground italic">
              Correlación no implica causalidad: úsalas como hipótesis de palanca.
            </p>
          </CardContent>
        </Card>
      </TabsContent>
    </Tabs>
  );
}
