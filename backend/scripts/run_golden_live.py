"""Runner en vivo del golden set — valida la única parte probabilística del sistema:
la traducción de lenguaje natural a llamadas de herramienta.

Pasa las 6 preguntas del brief (+ contexto de negocio y memoria conversacional)
por el agente real (Claude) y verifica:
  - que se llamó la herramienta esperada (con parámetros clave cuando aplica),
  - que se emitieron visualizaciones y narración sin errores,
  - términos ancla en la respuesta (laxos a propósito: la prosa varía, los datos no).

Costo aproximado de la corrida completa: ~USD 0.15-0.25 (Sonnet 4.6).
Ejecutar desde backend/:  .venv/bin/python scripts/run_golden_live.py
"""
from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from agent import stream_agent  # noqa: E402

# (nombre, pregunta, herramientas esperadas (alguna), términos ancla en la narración,
#  validador opcional de inputs de herramienta)
CASES = [
    (
        "1 filtrado",
        "¿Cuáles son las 5 zonas con mayor % Lead Penetration esta semana?",
        {"query_metrics"},
        r"(chiautempan|tlx|93)",
        lambda calls: any(c["name"] == "query_metrics" and c["input"].get("top_n") == 5 for c in calls),
    ),
    (
        "2 comparación",
        "Compara el Perfect Order entre zonas Wealthy y Non Wealthy en México",
        {"compare_segments"},
        r"wealthy",
        lambda calls: any(
            c["name"] == "compare_segments"
            and c["input"].get("dimension") == "ZONE_TYPE"
            and (c["input"].get("filters") or {}).get("country") == "MX"
            for c in calls
        ),
    ),
    (
        "3 tendencia",
        "Muestra la evolución de Gross Profit UE en Chapinero últimas 8 semanas",
        {"get_trend"},
        r"chapinero",
        None,
    ),
    (
        "4 agregación",
        "¿Cuál es el promedio de Lead Penetration por país?",
        {"aggregate_metric"},
        r"(país|pais|countr)",
        lambda calls: any(
            c["name"] == "aggregate_metric" and c["input"].get("group_by") == "COUNTRY" for c in calls
        ),
    ),
    (
        "5 multivariable",
        "¿Qué zonas tienen alto Lead Penetration pero bajo Perfect Order?",
        {"cross_metric_analysis"},
        r"(penetration|perfect)",
        None,
    ),
    (
        "6 inferencia",
        "¿Cuáles son las zonas que más crecen en órdenes en las últimas 5 semanas y qué podría explicar el crecimiento?",
        {"growth_analysis"},
        r"(cuenca|sabaneta)",
        None,
    ),
    (
        "9 nivel-2 SQL",
        "¿Cuál es la mediana de Perfect Orders por ciudad en Colombia esta semana?",
        {"run_sql"},
        r"(mediana|percentil|pasto)",
        None,
    ),
    (
        "7 ctx negocio",
        "¿Qué zonas problemáticas hay en Colombia?",
        {"query_metrics", "cross_metric_analysis", "get_trend", "aggregate_metric", "growth_analysis"},
        r"(colombia|co\b)",
        lambda calls: all(
            (c["input"].get("filters") or {}).get("country") in ("CO", None) for c in calls
        ),
    ),
]

FOLLOW_UP = (
    "8 memoria",
    "¿Y cuáles son las 5 peores en esa misma métrica?",
    {"query_metrics"},
    r"(peor|menor|bajo)",
    lambda calls: any(
        c["name"] == "query_metrics"
        and c["input"].get("ascending") is True
        and "lead" in str(c["input"].get("metric", "")).lower()
        for c in calls
    ),
)


async def run_case(messages: list[dict], question: str) -> dict:
    """Ejecuta una pregunta y devuelve lo observado + el historial resultante."""
    out = {"tools": [], "charts": 0, "tables": 0, "text": "", "error": None,
           "usage": {}, "messages": None, "tier": None}
    history = messages + [{"role": "user", "content": question}]
    async for ev in stream_agent(history):
        t = ev["type"]
        if t == "tool" and ev.get("status") == "running":
            out["tools"].append({"name": ev["name"], "input": ev.get("input") or {}})
        elif t == "chart":
            out["charts"] += 1
        elif t == "table":
            out["tables"] += 1
        elif t == "token":
            out["text"] += ev["text"]
        elif t == "error":
            out["error"] = ev["message"]
        elif t == "done":
            out["usage"] = ev.get("usage", {})
            out["messages"] = ev["messages"]
            out["tier"] = ev.get("tier")
    return out


def cost_usd(u: dict) -> float:
    return (
        u.get("input_tokens", 0) * 3e-6
        + u.get("cache_creation_input_tokens", 0) * 3.75e-6
        + u.get("cache_read_input_tokens", 0) * 0.3e-6
        + u.get("output_tokens", 0) * 15e-6
    )


def evaluate(case, result) -> list[str]:
    name, _q, expected_tools, anchor, input_check = case
    problems = []
    if result["error"]:
        problems.append(f"error: {result['error'][:80]}")
    used = {c["name"] for c in result["tools"]}
    if not used & expected_tools:
        problems.append(f"herramienta esperada {expected_tools}, usadas {used or '∅'}")
    if not result["text"].strip():
        problems.append("sin narración")
    elif not re.search(anchor, result["text"], re.IGNORECASE):
        problems.append(f"ancla /{anchor}/ ausente en la narración")
    if result["charts"] + result["tables"] == 0:
        problems.append("sin visualizaciones")
    if input_check and not input_check(result["tools"]):
        problems.append("parámetros de herramienta no cumplen lo esperado")
    expected_tier = "generated" if "run_sql" in expected_tools else "verified"
    if result.get("tier") != expected_tier:
        problems.append(f"tier {result.get('tier')!r}, esperado {expected_tier!r}")
    return problems


async def main() -> int:
    print(f"{'caso':14} {'herramientas':34} {'viz':>5} {'palabras':>8} {'USD':>8}  veredicto")
    print("-" * 92)
    total_cost, failures = 0.0, 0
    case1_messages = None

    for case in CASES:
        name, question = case[0], case[1]
        t0 = time.time()
        result = await run_case([], question)
        problems = evaluate(case, result)
        if name.startswith("1"):
            case1_messages = result["messages"]  # base para el test de memoria
        c = cost_usd(result["usage"])
        total_cost += c
        tools = ",".join(dict.fromkeys(t["name"] for t in result["tools"])) or "—"
        words = len(result["text"].split())
        verdict = "PASS" if not problems else "FAIL: " + "; ".join(problems)
        failures += bool(problems)
        print(f"{name:14} {tools[:34]:34} {result['charts'] + result['tables']:>5} {words:>8} {c:>8.4f}  {verdict}  ({time.time()-t0:.1f}s)")

    # Caso 8: memoria conversacional — continúa la sesión del caso 1
    if case1_messages:
        t0 = time.time()
        result = await run_case(case1_messages, FOLLOW_UP[1])
        problems = evaluate(FOLLOW_UP, result)
        c = cost_usd(result["usage"])
        total_cost += c
        tools = ",".join(dict.fromkeys(t["name"] for t in result["tools"])) or "—"
        verdict = "PASS" if not problems else "FAIL: " + "; ".join(problems)
        failures += bool(problems)
        print(f"{FOLLOW_UP[0]:14} {tools[:34]:34} {result['charts'] + result['tables']:>5} {len(result['text'].split()):>8} {c:>8.4f}  {verdict}  ({time.time()-t0:.1f}s)")

    print("-" * 92)
    print(f"costo total de la corrida: ${total_cost:.4f} USD · fallos: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
