"""Detectores estadísticos deterministas — Sistema de Insights Automáticos.

Sin LLM: toda la detección y el cálculo es pandas/numpy reproducible. El LLM
(en report.py) solo redacta la narrativa a partir de estos hallazgos ya calculados.

Categorías (brief §2.2):
  - anomaly      : cambio WoW > ±10% (semana -1 → 0), respetando la dirección de la métrica.
  - trend        : deterioro sostenido 3+ semanas consecutivas (dirección del catálogo).
  - benchmark    : zona divergente >1.5σ respecto a su peer group (mismo COUNTRY + ZONE_TYPE).
  - opportunity  : zona High Priority por debajo de la mediana de sus peers.
  - correlation  : relaciones Spearman fuertes entre métricas (GP UE winsorizado p1/p99).
  - quality      : zonas con flag OUT_OF_RANGE (la calidad del dato es un insight en sí mismo).

Ranking por **impacto ponderado por volumen de órdenes**: una caída en una zona de
270k órdenes pesa más que la misma caída en una de 200. impact = points · (1 + ln(1+órdenes)).
Los detectores excluyen QUALITY_FLAG != OK; las zonas flagged se reportan aparte (quality).
"""
from __future__ import annotations

import math
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from query_engine import CATALOG, _metrics, _orders  # noqa: E402

METRICS = [m for m in CATALOG["metrics"] if m != "Orders"]
WEEKS = list(range(-8, 1))  # -8 .. 0

# Umbrales (declarados explícitamente para defensa en Q&A)
WOW_THRESHOLD = 10.0      # % cambio WoW para anomalía
TREND_MIN_WEEKS = 3       # semanas consecutivas para tendencia preocupante
SIGMA_THRESHOLD = 1.5     # desviaciones para benchmarking
PEER_MIN = 5              # tamaño mínimo de peer group
OPP_GAP_PCT = 10.0        # gap % vs mediana de peers para oportunidad
CORR_MIN_RHO = 0.35       # |Spearman| mínimo para reportar correlación
CORR_MIN_N = 50           # pares mínimos para una correlación
MIN_BASE_FRAC = 0.10      # base previa mínima = fracción del IQR → mata % explosivos sobre ~0
GPUE = "Gross Profit UE"  # única métrica con outliers extremos / base cercana a cero


def _hib(metric: str) -> bool:
    return CATALOG["metrics"][metric].get("higher_is_better", True)


def _orders0() -> dict:
    o = _orders()
    s = o[o.WEEK == 0].groupby(["COUNTRY", "CITY", "ZONE"]).VALUE.sum()
    return s.to_dict()


@lru_cache(maxsize=1)
def _gpue_bounds() -> tuple[float, float]:
    """Cota p1/p99 de Gross Profit UE (OK, todas las semanas) para winsorizar sus outliers."""
    s = _metrics().query("METRIC == @GPUE and QUALITY_FLAG == 'OK'").VALUE.dropna()
    return float(s.quantile(0.01)), float(s.quantile(0.99))


@lru_cache(maxsize=1)
def _scales() -> dict:
    """Escala robusta (IQR) de cada métrica en la semana 0 (post-winsor GP UE).
    Sirve de piso de movimiento absoluto: filtra el ruido de % sobre bases ~0."""
    df = _clean_df0()
    iqr = df.groupby("METRIC").VALUE.apply(lambda s: float(s.quantile(0.75) - s.quantile(0.25)))
    return iqr.to_dict()


@lru_cache(maxsize=1)
def _clean_df0() -> pd.DataFrame:
    """Filas de la semana 0 (OK, sin nulos) con GP UE winsorizado a p1/p99."""
    m = _metrics()
    df = m[(m.WEEK == 0) & (m.QUALITY_FLAG == "OK")].dropna(subset=["VALUE"]).copy()
    mask = df.METRIC == GPUE
    if mask.any():
        lo, hi = _gpue_bounds()
        df.loc[mask, "VALUE"] = df.loc[mask, "VALUE"].clip(lo, hi)
    return df


def _pivot(metric: str) -> pd.DataFrame:
    df = _metrics()
    df = df[(df.METRIC == metric) & (df.QUALITY_FLAG == "OK")]
    piv = df.pivot_table(
        index=["COUNTRY", "CITY", "ZONE", "ZONE_TYPE", "ZONE_PRIORITIZATION"],
        columns="WEEK",
        values="VALUE",
    ).reindex(columns=WEEKS)
    if metric == GPUE:  # winsorizar para que un outlier no domine anomalías/tendencias
        lo, hi = _gpue_bounds()
        piv = piv.clip(lo, hi)
    return piv


# ----------------------------------------------------------- finding builder
def _severity(points: float) -> str:
    return "high" if points >= 50 else "medium" if points >= 25 else "low"


_REC = {
    "anomaly": "Revisar qué cambió en la zona la última semana (operación, supply, pricing) y aislar la causa del salto WoW.",
    "trend": "Abrir un caso de seguimiento: el deterioro es sostenido, no ruido. Priorizar por volumen de órdenes.",
    "benchmark": "Comparar la zona con sus peers (mismo país y tipo) para identificar la palanca que la separa del grupo.",
    "opportunity": "Zona estratégica (High Priority) bajo la mediana de sus peers: mayor retorno esperado al cerrar la brecha.",
    "correlation": "Usar la relación como hipótesis de palanca: mover la métrica líder podría arrastrar a la correlacionada.",
    "quality": "Sanear el dato en origen antes de tomar decisiones sobre estas zonas; se excluyen de los rankings por defecto.",
}


def _finding(category, metric, *, points, orders=0, evidence="", direction=None,
             country=None, city=None, zone=None, zone_type=None, prioritization=None,
             scope="zone", extra=None) -> dict:
    points = round(float(min(points, 100.0)), 1)
    vol_w = 1.0 + math.log1p(max(int(orders or 0), 0))
    f = {
        "category": category,
        "scope": scope,
        "metric": metric,
        "direction": direction,
        "country": country,
        "city": city,
        "zone": zone,
        "zone_type": zone_type,
        "prioritization": prioritization,
        "orders": int(orders or 0),
        "points": points,
        "impact_score": round(points * vol_w, 1),
        "severity": _severity(points),
        "evidence": evidence,
        "recommendation": _REC.get(category, ""),
    }
    if extra:
        f.update(extra)
    return f


# ================================================================ detectors
def detect_anomalies() -> list[dict]:
    """Cambios WoW > ±10% (semana -1 → 0), deterioro o mejora."""
    o0 = _orders0()
    out = []
    for metric in METRICS:
        piv = _pivot(metric)
        if 0 not in piv.columns or -1 not in piv.columns:
            continue
        cur, prev = piv[0], piv[-1]
        delta = ((cur - prev) / prev.abs() * 100).dropna()
        hib = _hib(metric)
        min_base = MIN_BASE_FRAC * _scales().get(metric, 0.0)
        for idx, d in delta.items():
            if abs(d) <= WOW_THRESHOLD:
                continue
            if abs(prev[idx]) < min_base:  # base ~0 → el % explota y no es señal real
                continue
            country, city, zone, ztype, prio = idx
            deteriorating = (d < 0) if hib else (d > 0)
            orders = int(o0.get((country, city, zone), 0))
            out.append(
                _finding(
                    "anomaly", metric, points=abs(d), orders=orders,
                    direction="deterioration" if deteriorating else "improvement",
                    country=country, city=city, zone=zone, zone_type=ztype, prioritization=prio,
                    evidence=f"{prev[idx]:.4g} → {cur[idx]:.4g} ({d:+.1f}% WoW)",
                    extra={"delta_pct": round(float(d), 1),
                           "value": round(float(cur[idx]), 4),
                           "prev_value": round(float(prev[idx]), 4)},
                )
            )
    return sorted(out, key=lambda f: f["impact_score"], reverse=True)


def detect_trends() -> list[dict]:
    """Deterioro sostenido 3+ semanas consecutivas terminando en la semana actual."""
    o0 = _orders0()
    out = []
    for metric in METRICS:
        piv = _pivot(metric)
        hib = _hib(metric)
        arr = piv.values
        diffs = np.diff(arr, axis=1)
        bad = (diffs < 0) if hib else (diffs > 0)
        bad = np.where(np.isnan(diffs), False, bad)
        streaks = np.cumprod(bad[:, ::-1], axis=1).sum(axis=1)  # consecutivas terminando en wk 0
        min_base = MIN_BASE_FRAC * _scales().get(metric, 0.0)
        for i, streak in enumerate(streaks):
            streak = int(streak)
            if streak < TREND_MIN_WEEKS:
                continue
            end = arr[i, -1]
            start = arr[i, -1 - streak]
            if not np.isfinite(start) or not np.isfinite(end) or start == 0:
                continue
            if abs(start) < min_base:  # base ~0 → el % total no es señal real
                continue
            total_pct = (end - start) / abs(start) * 100
            country, city, zone, ztype, prio = piv.index[i]
            orders = int(o0.get((country, city, zone), 0))
            out.append(
                _finding(
                    "trend", metric, points=abs(total_pct) + 5 * streak, orders=orders,
                    direction="deterioration",
                    country=country, city=city, zone=zone, zone_type=ztype, prioritization=prio,
                    evidence=f"{streak} semanas en deterioro ({start:.4g} → {end:.4g}, {total_pct:+.1f}%)",
                    extra={"weeks": streak, "total_change_pct": round(float(total_pct), 1),
                           "value": round(float(end), 4)},
                )
            )
    return sorted(out, key=lambda f: f["impact_score"], reverse=True)


def detect_benchmark() -> list[dict]:
    """Zonas que divergen >1.5σ (hacia el lado malo) de su peer group COUNTRY+ZONE_TYPE.
    GP UE se winsoriza solo para el cálculo del z (que un outlier no capture todo el grupo);
    el valor real se conserva y se etiqueta '(winsor.)' cuando se reporta el tope."""
    o0 = _orders0()
    m = _metrics()
    df0 = m[(m.WEEK == 0) & (m.QUALITY_FLAG == "OK")].dropna(subset=["VALUE"]).copy()
    lo, hi = _gpue_bounds()
    df0["VAL_STAT"] = df0["VALUE"]
    gp = df0.METRIC == GPUE
    df0.loc[gp, "VAL_STAT"] = df0.loc[gp, "VALUE"].clip(lo, hi)
    out = []
    for metric in METRICS:
        sub = df0[df0.METRIC == metric].copy()
        if sub.empty:
            continue
        stats = sub.groupby(["COUNTRY", "ZONE_TYPE"]).VAL_STAT.agg(["mean", "std", "count"])
        sub = sub.merge(stats, on=["COUNTRY", "ZONE_TYPE"])
        sub = sub[(sub["count"] >= PEER_MIN) & (sub["std"] > 0)]
        if sub.empty:
            continue
        sub["z"] = (sub.VAL_STAT - sub["mean"]) / sub["std"]
        hib = _hib(metric)
        bad = sub[sub.z < -SIGMA_THRESHOLD] if hib else sub[sub.z > SIGMA_THRESHOLD]
        for _, r in bad.iterrows():
            orders = int(o0.get((r.COUNTRY, r.CITY, r.ZONE), 0))
            clamped = bool(metric == GPUE and (r.VALUE < lo or r.VALUE > hi))
            shown = f"{r.VAL_STAT:.4g} (winsor.)" if clamped else f"{r.VALUE:.4g}"
            out.append(
                _finding(
                    "benchmark", metric, points=abs(r.z) * 12, orders=orders,
                    direction="deterioration", scope="zone",
                    country=r.COUNTRY, city=r.CITY, zone=r.ZONE,
                    zone_type=r.ZONE_TYPE, prioritization=r.ZONE_PRIORITIZATION,
                    evidence=f"{shown} vs media peers {r['mean']:.4g} (z={r.z:+.1f}, n={int(r['count'])})",
                    extra={"z_score": round(float(r.z), 2), "value": round(float(r.VALUE), 4),
                           "peer_mean": round(float(r["mean"]), 4), "peer_n": int(r["count"])},
                )
            )
    return sorted(out, key=lambda f: f["impact_score"], reverse=True)


def detect_opportunities() -> list[dict]:
    """Zonas High Priority por debajo de la mediana de sus peers (COUNTRY+ZONE_TYPE)."""
    o0 = _orders0()
    df0 = _clean_df0()  # GP UE winsorizado
    out = []
    for metric in METRICS:
        sub = df0[df0.METRIC == metric]
        if sub.empty:
            continue
        peer_med = sub.groupby(["COUNTRY", "ZONE_TYPE"]).VALUE.median().rename("peer_median")
        hp = sub[sub.ZONE_PRIORITIZATION == "High Priority"].merge(
            peer_med, on=["COUNTRY", "ZONE_TYPE"]
        )
        hib = _hib(metric)
        for _, r in hp.iterrows():
            if r.peer_median == 0:
                continue
            gap_pct = (r.peer_median - r.VALUE) / abs(r.peer_median) * 100
            if not hib:
                gap_pct = -gap_pct  # métrica de costo: estar por encima de la mediana es la brecha
            if gap_pct <= OPP_GAP_PCT:
                continue
            orders = int(o0.get((r.COUNTRY, r.CITY, r.ZONE), 0))
            out.append(
                _finding(
                    "opportunity", metric, points=gap_pct, orders=orders,
                    direction="deterioration",
                    country=r.COUNTRY, city=r.CITY, zone=r.ZONE,
                    zone_type=r.ZONE_TYPE, prioritization="High Priority",
                    evidence=f"{r.VALUE:.4g} vs mediana peers {r.peer_median:.4g} ({gap_pct:+.1f}% bajo objetivo)",
                    extra={"gap_pct": round(float(gap_pct), 1), "value": round(float(r.VALUE), 4),
                           "peer_median": round(float(r.peer_median), 4)},
                )
            )
    return sorted(out, key=lambda f: f["impact_score"], reverse=True)


def detect_correlations() -> list[dict]:
    """Correlaciones Spearman fuertes entre métricas (GP UE winsorizado p1/p99)."""
    m = _metrics()
    df0 = m[(m.WEEK == 0) & (m.QUALITY_FLAG == "OK")].dropna(subset=["VALUE"])
    wide = df0.pivot_table(index=["COUNTRY", "CITY", "ZONE"], columns="METRIC", values="VALUE")
    if "Gross Profit UE" in wide.columns:  # winsorizar outliers extremos antes de correlacionar
        s = wide["Gross Profit UE"]
        wide["Gross Profit UE"] = s.clip(s.quantile(0.01), s.quantile(0.99))
    corr = wide.corr(method="spearman", min_periods=CORR_MIN_N)
    out = []
    cols = list(corr.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            rho = corr.iloc[i, j]
            if pd.isna(rho) or abs(rho) < CORR_MIN_RHO:
                continue
            a, b = cols[i], cols[j]
            n = int(wide[[a, b]].dropna().shape[0])
            if n < CORR_MIN_N:
                continue
            sign = "misma dirección" if rho > 0 else "dirección opuesta"
            out.append(
                _finding(
                    "correlation", f"{a} ~ {b}", points=abs(rho) * 40, orders=0, scope="portfolio",
                    direction="positive" if rho > 0 else "negative",
                    evidence=f"Spearman ρ={rho:+.2f} ({sign}, n={n})",
                    extra={"metric_a": a, "metric_b": b, "rho": round(float(rho), 3), "n": n},
                )
            )
    return sorted(out, key=lambda f: f["impact_score"], reverse=True)


def detect_quality() -> list[dict]:
    """Zonas con flag OUT_OF_RANGE — la confiabilidad del dato es un insight propio."""
    m = _metrics()
    flagged = m[(m.QUALITY_FLAG != "OK")]
    if flagged.empty:
        return []
    out = []
    for metric, g in flagged.groupby("METRIC"):
        zones = g[["COUNTRY", "CITY", "ZONE"]].drop_duplicates()
        by_country = zones.COUNTRY.value_counts().to_dict()
        n = int(zones.shape[0])
        total = _metrics()[_metrics().METRIC == metric][["COUNTRY", "CITY", "ZONE"]].drop_duplicates().shape[0]
        share = n / total * 100 if total else 0
        out.append(
            _finding(
                "quality", metric, points=min(share, 40), orders=0, scope="portfolio",
                evidence=f"{n} zonas con valores fuera de rango ({share:.1f}% de la métrica); concentración: {by_country}",
                extra={"flagged_zones": n, "share_pct": round(share, 1), "by_country": by_country},
            )
        )
    return sorted(out, key=lambda f: f["impact_score"], reverse=True)


def heatmap_matrix() -> dict:
    """Matriz país × métrica para el heatmap de /insights: promedio simple por país
    (semana 0, flags excluidos, GP UE winsorizado) + score 0-1 normalizado min-max
    dentro de cada métrica, invertido cuando lower-is-better (1 = mejor siempre)."""
    df = _clean_df0()
    g = df.groupby(["METRIC", "COUNTRY"]).VALUE.mean().rename("value").reset_index()
    cells = []
    for metric, sub in g.groupby("METRIC"):
        vmin, vmax = float(sub.value.min()), float(sub.value.max())
        rng = vmax - vmin
        hib = _hib(metric)
        for _, r in sub.iterrows():
            pct = 0.5 if rng == 0 else (float(r.value) - vmin) / rng
            cells.append({
                "metric": metric,
                "country": r.COUNTRY,
                "value": round(float(r.value), 4),
                "score": round(pct if hib else 1 - pct, 3),
            })
    present = set(g.METRIC)
    return {
        "metrics": [m for m in METRICS if m in present],
        "countries": sorted(df.COUNTRY.unique().tolist()),
        "cells": cells,
        "formats": {m: CATALOG["metrics"][m]["format"] for m in METRICS},
    }


def run_all_detectors() -> dict[str, list[dict]]:
    return {
        "anomaly": detect_anomalies(),
        "trend": detect_trends(),
        "benchmark": detect_benchmark(),
        "opportunity": detect_opportunities(),
        "correlation": detect_correlations(),
        "quality": detect_quality(),
    }
