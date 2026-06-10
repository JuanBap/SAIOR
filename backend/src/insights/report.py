"""Reporte ejecutivo de insights.

build_report()  -> estructura JSON (resumen + top hallazgos + detalle por categoría + calidad).
to_markdown()   -> reporte ejecutivo en Markdown, 100% determinista (no necesita LLM).
narrate()       -> resumen ejecutivo redactado por Claude SOLO a partir de los números ya
                   calculados (opcional; requiere ANTHROPIC_API_KEY).

El cálculo y el ranking son deterministas; el LLM, si se usa, solo aporta prosa ejecutiva.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from query_engine import CATALOG, VALID_COUNTRIES, _metrics  # noqa: E402
from insights.detectors import (  # noqa: E402
    CORR_MIN_RHO, PEER_MIN, SIGMA_THRESHOLD, TREND_MIN_WEEKS, WOW_THRESHOLD,
    heatmap_matrix, run_all_detectors,
)

_CAT_TITLE = {
    "anomaly": "🔻 Anomalías (cambios WoW > ±10%)",
    "trend": f"📉 Tendencias preocupantes ({TREND_MIN_WEEKS}+ semanas de deterioro)",
    "benchmark": f"🧭 Benchmarking de peers (>{SIGMA_THRESHOLD}σ vs mismo país y tipo)",
    "opportunity": "🎯 Oportunidades (zonas High Priority bajo la mediana de sus peers)",
    "correlation": "🔗 Correlaciones entre métricas",
    "quality": "⚠️ Calidad de datos",
}
_CAT_ORDER = ["anomaly", "trend", "benchmark", "opportunity", "correlation", "quality"]


def _loc(f: dict) -> str:
    parts = [p for p in (f.get("city"), f.get("zone")) if p]
    base = " / ".join(parts) if parts else "—"
    return f"{base} ({f['country']})" if f.get("country") else base


# ================================================================ build
def build_report(*, top_overall: int = 6, top_per_cat: int = 5, generated_at: str | None = None) -> dict:
    cats = run_all_detectors()
    n_total = sum(len(v) for v in cats.values())

    # Pool crítico: hallazgos a nivel zona que representan PROBLEMAS (excluye mejoras).
    pool = [
        f
        for cat in ("anomaly", "trend", "benchmark", "opportunity")
        for f in cats[cat]
        if f.get("direction") != "improvement"
    ]
    pool.sort(key=lambda f: f["impact_score"], reverse=True)

    # Top global deduplicado por (zona, métrica): no repetir la misma zona 4 veces.
    seen: set = set()
    top: list[dict] = []
    for f in pool:
        key = (f.get("country"), f.get("city"), f.get("zone"), f.get("metric"))
        if key in seen:
            continue
        seen.add(key)
        top.append(f)
        if len(top) >= top_overall:
            break

    positives = [f for f in cats["anomaly"] if f.get("direction") == "improvement"][:3]
    n_zones = int(_metrics()[["COUNTRY", "CITY", "ZONE"]].drop_duplicates().shape[0])

    return {
        "generated_at": generated_at or datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "total_findings": n_total,
            "high_severity": sum(1 for f in pool if f["severity"] == "high"),
            "by_category": {k: len(v) for k, v in cats.items()},
        },
        "top_findings": top,
        "positive_signals": positives,
        "by_category": {k: cats[k][:top_per_cat] for k in _CAT_ORDER},
        "heatmap": heatmap_matrix(),
        "quality": cats["quality"],
        "coverage": {"zones": n_zones, "countries": VALID_COUNTRIES, "weeks": "-8 a 0 (8 semanas)"},
        "methodology": {
            "impact_formula": "impact = severidad(0-100) × (1 + ln(1 + órdenes_semana_0))",
            "thresholds": {
                "anomaly_wow_pct": WOW_THRESHOLD,
                "trend_min_weeks": TREND_MIN_WEEKS,
                "benchmark_sigma": SIGMA_THRESHOLD,
                "peer_min_size": PEER_MIN,
                "correlation_min_rho": CORR_MIN_RHO,
            },
            "notes": [
                "Gross Profit UE winsorizado a p1/p99 para que un outlier no domine.",
                "Las anomalías exigen una base previa ≥10% del IQR (evita % explosivos sobre ~0).",
                "Se excluyen valores con flag OUT_OF_RANGE; la calidad se reporta como sección propia.",
                "Correlación no implica causalidad: las relaciones son hipótesis de palanca.",
            ],
        },
    }


# ================================================================ markdown
def _fmt(metric: str, v) -> str:
    spec = CATALOG["metrics"].get(metric, {})
    fmt = spec.get("format")
    try:
        if fmt == "percent":
            return f"{v * 100:.1f}%"
        if fmt == "decimal_2":
            return f"{v:.2f}"
        if fmt == "integer":
            return f"{int(v):,}"
    except (TypeError, ValueError):
        pass
    return f"{v:.4g}" if isinstance(v, (int, float)) else str(v)


def to_markdown(report: dict) -> str:
    s = report["summary"]
    L: list[str] = []
    L.append("# 📊 Reporte Ejecutivo de Insights — Operaciones Rappi")
    L.append(
        f"_Generado: {report['generated_at']} · {s['total_findings']} hallazgos "
        f"({s['high_severity']} de severidad alta) · {report['coverage']['zones']} zonas · "
        f"{len(report['coverage']['countries'])} países_\n"
    )

    # Resumen ejecutivo
    L.append("## Resumen ejecutivo")
    L.append("Hallazgos más críticos, **ponderados por volumen de órdenes** (mayor impacto de negocio primero):\n")
    for i, f in enumerate(report["top_findings"], 1):
        L.append(
            f"{i}. **[{f['severity'].upper()}] {f['metric']}** — {_loc(f)} · {f['evidence']} "
            f"· {f['orders']:,} órdenes\n   ↳ _{f['recommendation']}_"
        )
    if report["positive_signals"]:
        L.append("\n**Señales positivas:** " + "; ".join(
            f"{f['metric']} en {_loc(f)} ({f['evidence']})" for f in report["positive_signals"]
        ))

    # Detalle por categoría
    L.append("\n## Detalle por categoría")
    for cat in _CAT_ORDER:
        items = report["by_category"].get(cat, [])
        total = s["by_category"].get(cat, 0)
        L.append(f"\n### {_CAT_TITLE[cat]} — {total}")
        if not items:
            L.append("_Sin hallazgos._")
            continue
        if cat == "correlation":
            L.append("| Métricas | ρ Spearman | n |")
            L.append("|---|---|---|")
            for f in items:
                L.append(f"| {f['metric_a']} ↔ {f['metric_b']} | {f['rho']:+.2f} | {f['n']} |")
        elif cat == "quality":
            for f in items:
                L.append(f"- **{f['metric']}**: {f['evidence']}")
        else:
            L.append("| Zona | Métrica | Evidencia | Órdenes | Impacto |")
            L.append("|---|---|---|---|---|")
            for f in items:
                L.append(f"| {_loc(f)} | {f['metric']} | {f['evidence']} | {f['orders']:,} | {f['impact_score']} |")
        if items and items[0].get("recommendation"):
            L.append(f"\n_Recomendación: {items[0]['recommendation']}_")

    # Metodología
    m = report["methodology"]
    L.append("\n## Metodología")
    L.append(f"- **Ranking de impacto**: `{m['impact_formula']}`.")
    for note in m["notes"]:
        L.append(f"- {note}")
    th = m["thresholds"]
    L.append(
        f"- **Umbrales**: anomalía ±{th['anomaly_wow_pct']}% WoW · tendencia {th['trend_min_weeks']}+ semanas · "
        f"benchmark {th['benchmark_sigma']}σ (peer mínimo {th['peer_min_size']}) · correlación |ρ|≥{th['correlation_min_rho']}."
    )
    return "\n".join(L)


# ================================================================ LLM narration (opcional)
_NARRATE_SYSTEM = (
    "Eres analista senior de Operaciones en Rappi. Redacta un resumen ejecutivo (2-3 párrafos, "
    "español, tono directo de negocio) a partir de los hallazgos YA CALCULADOS que se te entregan. "
    "Reglas: usa SOLO los números presentes en el JSON; no inventes cifras ni zonas; prioriza por "
    "impacto (ya viene ponderado por volumen de órdenes); cierra con las 2-3 acciones más urgentes."
)


def narrate(report: dict, *, model: str | None = None) -> str:
    """Resumen ejecutivo redactado por Claude desde los números ya calculados. Requiere API key."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return ""
    import anthropic

    payload = {
        "summary": report["summary"],
        "top_findings": [
            {k: f.get(k) for k in ("metric", "severity", "evidence", "orders", "category", "recommendation")}
            | {"location": _loc(f)}
            for f in report["top_findings"]
        ],
        "positive_signals": [{"metric": f["metric"], "evidence": f["evidence"]} for f in report["positive_signals"]],
    }
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        max_tokens=900,
        temperature=0,
        system=_NARRATE_SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()


if __name__ == "__main__":  # genera el reporte a stdout: python -m insights.report
    print(to_markdown(build_report()))
