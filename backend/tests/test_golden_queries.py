"""Golden test set — los 6 casos de uso del brief contra el query engine.

Estos valores se calcularon con el engine sobre el dataset procesado (flags de
calidad derivados del valid_range del catálogo) y quedan CONGELADOS como
regresión: si una refactorización cambia un número, la suite lo detecta.

La traducción NL→herramienta (la única parte probabilística) se valida aparte
con scripts/run_golden_live.py, que pasa las preguntas reales por el agente.
"""
import math

import pytest

import query_engine as qe

approx = lambda v, tol=1e-4: pytest.approx(v, abs=tol)  # noqa: E731


# ---------------------------------------------------------------- caso 1: filtrado
def test_case1_top5_lead_penetration_this_week():
    """'¿Cuáles son las 5 zonas con mayor % Lead Penetration esta semana?'"""
    r = qe.query_metrics("Lead Penetration", top_n=5)
    zones = [(x["ZONE"], x["VALUE"]) for x in r["results"]]
    assert zones == [
        ("TLX CHIAUTEMPAN", approx(0.9326)),
        ("GUA_SUR", approx(0.922)),
        ("ZAC Tres Cruces", approx(0.8079)),
        ("Gonnet", approx(0.7912)),
        ("Pinares Sur", approx(0.6954)),
    ]
    # Ningún valor imposible (>100%) puede colarse en el ranking por defecto
    assert all(x["VALUE"] <= 1.0 for x in r["results"])
    assert r["n_zones_universe"] == 899
    assert "32 zonas excluidas" in r["quality_warning"]


# ------------------------------------------------------------- caso 2: comparación
def test_case2_perfect_orders_wealthy_vs_nonwealthy_mx():
    """'Compara el Perfect Order entre zonas Wealthy y Non Wealthy en México'"""
    r = qe.compare_segments("Perfect Orders", "ZONE_TYPE", filters={"country": "MX"})
    segs = r["segments"]
    assert segs["Wealthy"]["mean"] == approx(0.9043)
    assert segs["Wealthy"]["count"] == 74
    assert segs["Non Wealthy"]["mean"] == approx(0.8666)
    assert segs["Non Wealthy"]["count"] == 228
    # Brecha de ~3.8 puntos a favor de Wealthy
    assert abs(segs["Wealthy"]["mean"] - segs["Non Wealthy"]["mean"]) == approx(0.0377)


# --------------------------------------------------------------- caso 3: tendencia
def test_case3_gross_profit_trend_chapinero():
    """'Muestra la evolución de Gross Profit UE en Chapinero últimas 8 semanas'"""
    r = qe.get_trend("Gross Profit UE", filters={"zone": "Chapinero"})
    s = r["series"]
    assert len(s) == 9 and [p["week"] for p in s] == list(range(-8, 1))
    assert s[0]["value"] == approx(2.9042)
    assert s[-2]["value"] == approx(3.4506)  # pico en la semana -1
    assert s[-1]["value"] == approx(2.9869)  # caída en la semana actual
    assert r["total_change_pct"] == approx(2.85, tol=0.01)
    assert r["n_zones_aggregated"] == 1
    assert r["chart_suggestion"] == "line"


# -------------------------------------------------------------- caso 4: agregación
def test_case4_avg_lead_penetration_by_country():
    """'¿Cuál es el promedio de Lead Penetration por país?'"""
    r = qe.aggregate_metric("Lead Penetration", "COUNTRY")
    means = {x["segment"]: x["mean"] for x in r["results"]}
    assert means == {
        "AR": approx(0.2612), "BR": approx(0.0925), "CL": approx(0.2644),
        "CO": approx(0.2533), "CR": approx(0.0473), "EC": approx(0.1486),
        "MX": approx(0.1824), "PE": approx(0.1386), "UY": approx(0.1136),
    }
    assert "32 valores OUT_OF_RANGE excluidos" in r["aggregation_note"]


# ----------------------------------------------------------- caso 5: multivariable
def test_case5_high_lead_pen_low_perfect_orders():
    """'¿Qué zonas tienen alto Lead Penetration pero bajo Perfect Order?'"""
    r = qe.cross_metric_analysis("Lead Penetration", "Perfect Orders")
    assert r["universe_size"] == 879
    assert r["n_found"] == 15
    assert r["spearman_correlation"] == approx(0.331, tol=0.001)
    assert r["thresholds"]["Lead Penetration >="] == approx(0.2461)
    assert r["thresholds"]["Perfect Orders <="] == approx(0.8396)
    # Todas las zonas devueltas cumplen la condición del cruce
    for row in r["results"]:
        assert row["Lead Penetration"] >= r["thresholds"]["Lead Penetration >="] - 1e-9
        assert row["Perfect Orders"] <= r["thresholds"]["Perfect Orders <="] + 1e-9


# ------------------------------------------------------------- caso 6: inferencia
def test_case6_growth_last_5_weeks_with_drivers():
    """'¿Qué zonas crecen más en órdenes en las últimas 5 semanas y qué lo explica?'"""
    r = qe.growth_analysis(weeks=5, top_n=3)
    top = [(x["ZONE"], x["GROWTH_PCT"]) for x in r["top_growing_zones"]]
    assert top == [
        ("Centro de cuenca", approx(46.94, tol=0.01)),
        ("Sabaneta", approx(37.38, tol=0.01)),
        ("Zazue", approx(26.15, tol=0.01)),
    ]
    # El contexto de drivers existe y se presenta como hipótesis, no causalidad
    assert r["avg_driver_metric_change_in_top_zones"]
    assert "no implica causalidad" in r["interpretation_note"]


# ----------------------------------------------- resolución determinista de entidades
def test_metric_aliases_resolve_in_spanish():
    assert qe.resolve_metric("penetración")[0] == "Lead Penetration"
    assert qe.resolve_metric("ordenes perfectas")[0] == "Perfect Orders"
    assert qe.resolve_metric("rentabilidad")[0] == "Gross Profit UE"
    assert qe.resolve_metric("markdowns")[0] == "Restaurants Markdowns / GMV"


def test_zone_resolution_fuzzy():
    hits = qe.resolve_zone("chapinero")
    assert hits[0] == {"COUNTRY": "CO", "CITY": "Bogota", "ZONE": "Chapinero"}


# ------------------------------------------------------- self-healing: errores útiles
def test_unknown_metric_returns_structured_error_with_suggestions():
    r = qe.query_metrics("Métrica Inventada")
    assert "error" in r and r["suggestions"]


def test_invalid_country_raises_with_valid_options():
    with pytest.raises(Exception, match="País inválido"):
        qe.query_metrics("Perfect Orders", filters={"country": "XX"})


def test_ambiguous_trend_asks_for_clarification():
    r = qe.get_trend("Perfect Orders", filters={"country": "CO"})
    assert "clarification_needed" in r and r["sample_zones"]


# --------------------------------------------------- invariantes de calidad de datos
def test_quality_flags_match_catalog_valid_range():
    """Ningún valor con flag OK puede violar el valid_range de su métrica."""
    m = qe._metrics()
    total_flagged = int((m.QUALITY_FLAG != "OK").sum())
    wk0_flagged = int(((m.QUALITY_FLAG != "OK") & (m.WEEK == 0)).sum())
    assert total_flagged == 253
    assert wk0_flagged == 32
    for metric, spec in qe.CATALOG["metrics"].items():
        vr = spec.get("valid_range")
        if not vr or metric == "Orders":
            continue
        lo, hi = vr
        ok = m[(m.METRIC == metric) & (m.QUALITY_FLAG == "OK")].VALUE.dropna()
        if lo is not None:
            assert (ok >= lo).all(), f"{metric}: valor OK bajo el rango"
        if hi is not None:
            assert (ok <= hi).all(), f"{metric}: valor OK sobre el rango"


def test_weighted_aggregate_runs_and_differs_from_simple():
    simple = qe.aggregate_metric("Perfect Orders", "COUNTRY")
    weighted = qe.aggregate_metric("Perfect Orders", "COUNTRY", weighted_by_orders=True)
    s = {x["segment"]: x["mean"] for x in simple["results"]}
    w = {x["segment"]: x["value"] for x in weighted["results"]}
    assert set(s) == set(w) == {"AR", "BR", "CL", "CO", "CR", "EC", "MX", "PE", "UY"}
    assert any(not math.isclose(s[k], w[k], abs_tol=1e-6) for k in s)
