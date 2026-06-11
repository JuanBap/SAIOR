"""Query Engine determinista — Sistema de Análisis Inteligente Rappi.

Principio: el LLM nunca toca los datos. Invoca estas herramientas con
parámetros validados (pydantic) y recibe JSON con resultados calculados
por pandas. Todo error de parámetros devuelve mensaje estructurado que
el agente usa para auto-corregirse.
"""
from __future__ import annotations

import difflib
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
CATALOG = json.loads((Path(__file__).parent / "metrics_catalog.json").read_text())

VALID_METRICS = [m for m in CATALOG["metrics"] if m != "Orders"]
VALID_COUNTRIES = CATALOG["dimensions"]["COUNTRY"]["values"]


# ---------------------------------------------------------------- data access
@lru_cache(maxsize=1)
def _metrics() -> pd.DataFrame:
    return pd.read_parquet(DATA / "metrics_long.parquet")


@lru_cache(maxsize=1)
def _orders() -> pd.DataFrame:
    return pd.read_parquet(DATA / "orders_long.parquet")


# ---------------------------------------------------------- entity resolution
def resolve_metric(name: str) -> tuple[Optional[str], list[str]]:
    """Resuelve un nombre de métrica (exacto, alias o fuzzy). Determinista."""
    if name in CATALOG["metrics"]:
        return name, []
    low = name.lower().strip()
    for metric, spec in CATALOG["metrics"].items():
        if low == metric.lower() or low in [a.lower() for a in spec.get("aliases", [])]:
            return metric, []
    candidates = difflib.get_close_matches(
        low, [m.lower() for m in CATALOG["metrics"]], n=3, cutoff=0.45
    )
    mapped = [m for m in CATALOG["metrics"] if m.lower() in candidates]
    return (mapped[0], mapped) if len(mapped) == 1 else (None, mapped)


def resolve_zone(text: str, country: Optional[str] = None) -> list[dict]:
    """Devuelve zonas candidatas para un texto libre (fuzzy, máx 5)."""
    df = _metrics()[["COUNTRY", "CITY", "ZONE"]].drop_duplicates()
    if country:
        df = df[df.COUNTRY == country]
    low = text.lower().strip()
    exact = df[df.ZONE.str.lower() == low]
    if len(exact):
        return exact.to_dict("records")
    mask = df.ZONE.str.lower().str.contains(low, regex=False) | df.CITY.str.lower().str.contains(low, regex=False)
    hits = df[mask]
    if len(hits) == 0:
        zl = df.ZONE.str.lower().tolist()
        close = difflib.get_close_matches(low, zl, n=5, cutoff=0.6)
        hits = df[df.ZONE.str.lower().isin(close)]
    return hits.head(5).to_dict("records")


# ------------------------------------------------------------------- schemas
class Filters(BaseModel):
    country: Optional[str] = Field(None, description="Código de país: AR,BR,CL,CO,CR,EC,MX,PE,UY")
    city: Optional[str] = None
    zone: Optional[str] = None
    zone_type: Optional[Literal["Wealthy", "Non Wealthy"]] = None
    zone_prioritization: Optional[Literal["High Priority", "Prioritized", "Not Prioritized"]] = None

    @field_validator("country")
    @classmethod
    def _c(cls, v):
        if v and v not in VALID_COUNTRIES:
            raise ValueError(f"País inválido '{v}'. Válidos: {VALID_COUNTRIES}")
        return v


def _apply_filters(df: pd.DataFrame, f: Filters) -> pd.DataFrame:
    if f.country:
        df = df[df.COUNTRY == f.country]
    if f.city:
        df = df[df.CITY.str.lower() == f.city.lower()]
    if f.zone:
        df = df[df.ZONE.str.lower() == f.zone.lower()]
    if f.zone_type and "ZONE_TYPE" in df:
        df = df[df.ZONE_TYPE == f.zone_type]
    if f.zone_prioritization and "ZONE_PRIORITIZATION" in df:
        df = df[df.ZONE_PRIORITIZATION == f.zone_prioritization]
    return df


def _metric_or_error(name: str):
    metric, suggestions = resolve_metric(name)
    if metric is None:
        return None, {
            "error": f"Métrica '{name}' no reconocida.",
            "suggestions": suggestions or VALID_METRICS,
        }
    return metric, None


def _fmt(metric: str) -> dict:
    spec = CATALOG["metrics"][metric]
    return {
        "metric": metric,
        "format": spec["format"],
        "higher_is_better": spec["higher_is_better"],
        "caveat": spec.get("caveat"),
    }


# ================================================================ TOOL 1
def query_metrics(
    metric: str,
    filters: dict | None = None,
    week: int = 0,
    top_n: int = 10,
    ascending: bool = False,
    min_orders: int | None = None,
    exclude_flagged: bool = True,
) -> dict:
    """Filtra y rankea zonas por una métrica en una semana dada.
    Cubre: '5 zonas con mayor Lead Penetration esta semana'.
    exclude_flagged=True descarta valores con flag de calidad OUT_OF_RANGE."""
    m, err = _metric_or_error(metric)
    if err:
        return err
    f = Filters(**(filters or {}))
    df = _apply_filters(_metrics(), f)
    df = df[(df.METRIC == m) & (df.WEEK == week)].dropna(subset=["VALUE"])
    n_flagged = int((df.QUALITY_FLAG != "OK").sum())
    if exclude_flagged:
        df = df[df.QUALITY_FLAG == "OK"]
    if min_orders:
        o = _orders()
        o = o[o.WEEK == week].groupby(["COUNTRY", "CITY", "ZONE"]).VALUE.sum().reset_index()
        o = o[o.VALUE >= min_orders][["COUNTRY", "CITY", "ZONE"]]
        df = df.merge(o, on=["COUNTRY", "CITY", "ZONE"])
    if df.empty:
        return {"error": "Sin datos para esos filtros.", "filters": f.model_dump()}
    out = df.sort_values("VALUE", ascending=ascending).head(top_n)
    return {
        **_fmt(m),
        "week": week,
        "n_zones_universe": int(len(df)),
        "results": out[
            ["COUNTRY", "CITY", "ZONE", "ZONE_TYPE", "ZONE_PRIORITIZATION", "VALUE", "QUALITY_FLAG"]
        ].round(4).to_dict("records"),
        "quality_warning": (
            f"{n_flagged} zonas excluidas por dato fuera de rango (flag OUT_OF_RANGE); usa exclude_flagged=false para incluirlas."
            if n_flagged and exclude_flagged else
            ("Resultados incluyen valores OUT_OF_RANGE." if (out.QUALITY_FLAG != "OK").any() else None)
        ),
    }


# ================================================================ TOOL 2
def compare_segments(
    metric: str,
    dimension: Literal["ZONE_TYPE", "ZONE_PRIORITIZATION", "COUNTRY", "CITY"],
    filters: dict | None = None,
    week: int = 0,
) -> dict:
    """Compara una métrica entre segmentos de una dimensión.
    Cubre: 'Perfect Order entre Wealthy y Non Wealthy en México'."""
    m, err = _metric_or_error(metric)
    if err:
        return err
    f = Filters(**(filters or {}))
    df = _apply_filters(_metrics(), f)
    df = df[(df.METRIC == m) & (df.WEEK == week)].dropna(subset=["VALUE"])
    if df.empty:
        return {"error": "Sin datos para esos filtros.", "filters": f.model_dump()}
    g = df.groupby(dimension).VALUE.agg(["mean", "median", "std", "count"]).round(4)
    segs = g.to_dict("index")
    gap = None
    if len(segs) == 2:
        ks = list(segs)
        gap = round(segs[ks[0]]["mean"] - segs[ks[1]]["mean"], 4)
    return {**_fmt(m), "week": week, "dimension": dimension,
            "segments": segs, "gap_mean_first_minus_second": gap}


# ================================================================ TOOL 3
def get_trend(
    metric: str,
    filters: dict | None = None,
    weeks: int = 8,
    aggregate: bool = False,
) -> dict:
    """Serie temporal de una métrica para una zona o agregado.
    Cubre: 'evolución de Gross Profit UE en Chapinero últimas 8 semanas'."""
    if metric.lower() in ("orders", "ordenes", "órdenes", "pedidos"):
        f = Filters(**(filters or {}))
        df = _apply_filters(_orders(), f)
        df = df[df.WEEK >= -weeks].dropna(subset=["VALUE"])
        if df.empty:
            return {"error": "Sin datos de órdenes para esos filtros."}
        s = df.groupby("WEEK").VALUE.sum()
        series = [{"week": int(w), "value": float(v)} for w, v in s.items()]
        chg = (s.iloc[-1] - s.iloc[0]) / s.iloc[0] if s.iloc[0] else None
        return {"metric": "Orders", "format": "integer", "series": series,
                "total_change_pct": round(float(chg) * 100, 2) if chg is not None else None}
    m, err = _metric_or_error(metric)
    if err:
        return err
    f = Filters(**(filters or {}))
    df = _apply_filters(_metrics(), f)
    df = df[(df.METRIC == m) & (df.WEEK >= -weeks)].dropna(subset=["VALUE"])
    if df.empty:
        return {"error": "Sin datos para esos filtros.", "filters": f.model_dump()}
    n_zones = df[["COUNTRY", "CITY", "ZONE"]].drop_duplicates().shape[0]
    if n_zones > 1 and not aggregate:
        return {"clarification_needed":
                f"{n_zones} zonas coinciden con el filtro. Especifica la zona o usa aggregate=true para promediar.",
                "sample_zones": df[["COUNTRY", "CITY", "ZONE"]].drop_duplicates().head(5).to_dict("records")}
    s = df.groupby("WEEK").VALUE.mean()
    series = [{"week": int(w), "value": round(float(v), 4)} for w, v in s.items()]
    chg = (s.iloc[-1] - s.iloc[0]) / abs(s.iloc[0]) if s.iloc[0] else None
    weekly = s.diff().dropna()
    return {**_fmt(m), "n_zones_aggregated": n_zones, "series": series,
            "total_change_pct": round(float(chg) * 100, 2) if chg is not None else None,
            "consecutive_declines": int((weekly < 0).astype(int)[::-1].cumprod().sum()),
            "chart_suggestion": "line"}


# ================================================================ TOOL 4
def aggregate_metric(
    metric: str,
    group_by: Literal["COUNTRY", "CITY", "ZONE_TYPE", "ZONE_PRIORITIZATION"],
    filters: dict | None = None,
    week: int = 0,
    weighted_by_orders: bool = False,
    exclude_flagged: bool = True,
) -> dict:
    """Agrega una métrica por dimensión. Cubre: 'promedio de Lead Penetration por país'.
    exclude_flagged=True descarta valores OUT_OF_RANGE para no distorsionar promedios."""
    m, err = _metric_or_error(metric)
    if err:
        return err
    f = Filters(**(filters or {}))
    df = _apply_filters(_metrics(), f)
    df = df[(df.METRIC == m) & (df.WEEK == week)].dropna(subset=["VALUE"])
    n_flagged = int((df.QUALITY_FLAG != "OK").sum())
    if exclude_flagged:
        df = df[df.QUALITY_FLAG == "OK"]
    if df.empty:
        return {"error": "Sin datos para esos filtros."}
    if weighted_by_orders:
        o = _orders()
        o = o[o.WEEK == week].rename(columns={"VALUE": "ORDERS"})
        df = df.merge(o[["COUNTRY", "CITY", "ZONE", "ORDERS"]], on=["COUNTRY", "CITY", "ZONE"], how="inner")
        df = df.dropna(subset=["ORDERS"])  # un solo peso NaN devolvería NaN para todo el grupo
        df = df[df.ORDERS > 0]
        g = df.groupby(group_by).apply(
            lambda x: round(float(np.average(x.VALUE, weights=x.ORDERS)), 4), include_groups=False
        )
        cov = "ponderado por órdenes (solo zonas con datos de órdenes)"
        results = [{"segment": k, "value": float(v)} for k, v in g.items()]
    else:
        g = df.groupby(group_by).VALUE.agg(["mean", "median", "count"]).round(4)
        cov = "promedio simple entre zonas"
        results = [{"segment": k, **v} for k, v in g.to_dict("index").items()]
    note = cov + (f"; {n_flagged} valores OUT_OF_RANGE excluidos" if n_flagged and exclude_flagged else "")
    return {**_fmt(m), "week": week, "group_by": group_by,
            "aggregation_note": note, "results": results, "chart_suggestion": "bar"}


# ================================================================ TOOL 5
def cross_metric_analysis(
    metric_high: str,
    metric_low: str,
    filters: dict | None = None,
    week: int = 0,
    quantile: float = 0.25,
    top_n: int = 15,
) -> dict:
    """Zonas con métrica A alta y métrica B baja (cuartiles del universo filtrado).
    Cubre: 'alto Lead Penetration pero bajo Perfect Order'."""
    mh, err = _metric_or_error(metric_high)
    if err:
        return err
    ml, err = _metric_or_error(metric_low)
    if err:
        return err
    f = Filters(**(filters or {}))
    df = _apply_filters(_metrics(), f)
    df = df[(df.WEEK == week) & (df.METRIC.isin([mh, ml])) & (df.QUALITY_FLAG == "OK")].dropna(subset=["VALUE"])
    wide = df.pivot_table(index=["COUNTRY", "CITY", "ZONE", "ZONE_TYPE"],
                          columns="METRIC", values="VALUE").dropna().reset_index()
    if wide.empty:
        return {"error": f"Sin zonas con ambas métricas ({mh}, {ml})."}
    hi_thr = wide[mh].quantile(1 - quantile)
    lo_thr = wide[ml].quantile(quantile)
    sel = wide[(wide[mh] >= hi_thr) & (wide[ml] <= lo_thr)].copy()
    sel["gap_score"] = (wide[mh].rank(pct=True) - wide[ml].rank(pct=True))
    sel = sel.sort_values("gap_score", ascending=False).head(top_n)
    corr = float(wide[mh].corr(wide[ml], method="spearman"))
    return {"metric_high": mh, "metric_low": ml, "week": week,
            "thresholds": {f"{mh} >=": round(float(hi_thr), 4), f"{ml} <=": round(float(lo_thr), 4)},
            "universe_size": int(len(wide)), "n_found": int(len(sel)),
            "spearman_correlation": round(corr, 3),
            "results": sel.drop(columns="gap_score").round(4).to_dict("records"),
            "chart_suggestion": "scatter"}


# ================================================================ TOOL 6
def growth_analysis(
    filters: dict | None = None,
    weeks: int = 5,
    top_n: int = 10,
    min_orders_base: int = 500,
) -> dict:
    """Zonas con mayor crecimiento en órdenes + contexto de métricas para hipótesis.
    Cubre: '¿qué zonas crecen más en órdenes y qué explica el crecimiento?'."""
    f = Filters(**(filters or {}))
    o = _apply_filters(_orders(), f)
    w0, w1 = -(weeks - 1), 0
    base = o[o.WEEK == w0].rename(columns={"VALUE": "BASE"})
    last = o[o.WEEK == w1].rename(columns={"VALUE": "LAST"})
    g = base.merge(last, on=["COUNTRY", "CITY", "ZONE"]).dropna(subset=["BASE", "LAST"])
    g = g[g.BASE >= min_orders_base]  # evita % explosivos en zonas minúsculas
    if g.empty:
        return {"error": "Sin zonas con órdenes suficientes para el análisis."}
    g["GROWTH_PCT"] = (g.LAST - g.BASE) / g.BASE * 100
    top = g.sort_values("GROWTH_PCT", ascending=False).head(top_n)

    # Contexto: cambio de métricas clave en las mismas zonas/ventana → hipótesis
    drivers = ["Lead Penetration", "Perfect Orders", "Restaurants Markdowns / GMV",
               "Pro Adoption (Last Week Status)", "Non-Pro PTC > OP",
               "% Restaurants Sessions With Optimal Assortment"]
    m = _metrics()
    keys = top[["COUNTRY", "CITY", "ZONE"]]
    ctx = m.merge(keys, on=["COUNTRY", "CITY", "ZONE"])
    ctx = ctx[ctx.METRIC.isin(drivers) & ctx.WEEK.isin([w0, w1])]
    piv = ctx.pivot_table(index=["COUNTRY", "CITY", "ZONE", "METRIC"],
                          columns="WEEK", values="VALUE").reset_index()
    piv["DELTA"] = piv.get(w1, np.nan) - piv.get(w0, np.nan)
    deltas = (piv.groupby("METRIC").DELTA.mean().dropna().round(4).to_dict())
    return {"window_weeks": weeks, "min_orders_base": min_orders_base,
            "top_growing_zones": top[["COUNTRY", "CITY", "ZONE", "BASE", "LAST", "GROWTH_PCT"]]
            .round(2).to_dict("records"),
            "avg_driver_metric_change_in_top_zones": deltas,
            "interpretation_note": ("DELTA promedio de métricas clave en las zonas top durante la misma "
                                    "ventana; correlación no implica causalidad — presentar como hipótesis."),
            "chart_suggestion": "bar"}


# ================================================================ TOOL 7
def get_schema_info() -> dict:
    """Esquema, catálogo y cobertura — el agente lo usa para orientarse."""
    m = _metrics()
    return {"metrics": {k: {kk: v[kk] for kk in ("definition", "format", "higher_is_better")
                            if kk in v} for k, v in CATALOG["metrics"].items()},
            "dimensions": CATALOG["dimensions"],
            "business_concepts": CATALOG["business_concepts"],
            "coverage": {"zones": int(m[["COUNTRY", "CITY", "ZONE"]].drop_duplicates().shape[0]),
                         "countries": VALID_COUNTRIES, "weeks": "-8 (hace 8 semanas) a 0 (actual)"}}


TOOL_REGISTRY = {
    "query_metrics": query_metrics,
    "compare_segments": compare_segments,
    "get_trend": get_trend,
    "aggregate_metric": aggregate_metric,
    "cross_metric_analysis": cross_metric_analysis,
    "growth_analysis": growth_analysis,
    "get_schema_info": get_schema_info,
    "resolve_zone": lambda text, country=None: {"candidates": resolve_zone(text, country)},
}
