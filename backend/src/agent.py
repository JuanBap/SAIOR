"""Agente conversacional — orquestador Claude + tool use.

Principio: el LLM nunca calcula. Traduce la pregunta en lenguaje natural a
llamadas de herramientas tipadas (query_engine), y narra la respuesta SOLO a
partir del JSON que devuelven esas herramientas. Todo número proviene de pandas.

Defensas contra el no-determinismo implementadas aquí:
  - Tool use con schemas (el LLM solo emite parámetros validados).
  - Catálogo semántico inyectado en el system prompt.
  - temperature=0 (Sonnet 4.6 lo soporta).
  - Self-healing: los errores estructurados del engine vuelven como tool_result
    y el modelo se corrige (acotado por MAX_ITERS).
  - Narración anclada: el system prompt prohíbe citar números fuera del JSON.

Los gráficos y tablas NO los inventa el LLM: se construyen de forma determinista
en `result_to_events` a partir del resultado real de cada herramienta y se
emiten como eventos SSE aparte. El LLM solo produce el texto narrado.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import AsyncIterator

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))  # resolver query_engine desde cualquier CWD
from query_engine import CATALOG, VALID_COUNTRIES, TOOL_REGISTRY  # noqa: E402

DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 4096
MAX_ITERS = 8  # tope de vueltas del loop de tool use por mensaje del usuario


# ============================================================ system prompt
def _render_catalog() -> str:
    lines = []
    for name, spec in CATALOG["metrics"].items():
        direction = "↑ mejor" if spec.get("higher_is_better") else "↓ mejor (métrica de costo)"
        aliases = ", ".join(spec.get("aliases", [])[:4])
        caveat = f" ⚠ {spec['caveat']}" if spec.get("caveat") else ""
        lines.append(
            f"- **{name}** ({spec['format']}, {direction}): {spec['definition']}."
            f"{' Aliases: ' + aliases + '.' if aliases else ''}{caveat}"
        )
    return "\n".join(lines)


def _render_concepts() -> str:
    return "\n".join(f"- **{k}**: {v}" for k, v in CATALOG["business_concepts"].items())


def build_system_prompt() -> str:
    return f"""Eres el asistente de datos de **Operaciones Rappi**. Ayudas a equipos no técnicos
(Strategy, Planning & Analytics y Operations) a obtener insights sobre métricas operacionales
de ~980 zonas en 9 países de LATAM (AR, BR, CL, CO, CR, EC, MX, PE, UY), con datos de las
últimas 8 semanas (WEEK va de -8 = hace 8 semanas a 0 = semana actual).

# Regla de oro (no negociable)
NUNCA calculas ni inventas números. Para CUALQUIER dato, llamas a una herramienta y narras
EXCLUSIVAMENTE a partir del JSON que devuelve. Si un número no está en el resultado de una
herramienta, no lo mencionas. No estimes, no promedies de memoria, no extrapoles.

# Catálogo de métricas (las únicas válidas)
{_render_catalog()}

# Dimensiones
- COUNTRY: {", ".join(VALID_COUNTRIES)} (acepta nombres: "México"→MX, "Colombia"→CO, etc.).
- ZONE_TYPE: Wealthy / Non Wealthy (segmentación por poder adquisitivo).
- ZONE_PRIORITIZATION: High Priority / Prioritized / Not Prioritized.
- WEEK: entero -8..0. "esta semana"=0, "semana pasada"=-1, "últimas 5 semanas"=-4..0.

# Conceptos de negocio (úsalos al interpretar preguntas vagas)
{_render_concepts()}

# Herramientas disponibles
- query_metrics: filtrar y rankear zonas por una métrica ("top 5 zonas con mayor X").
- compare_segments: comparar una métrica entre segmentos ("X entre Wealthy y Non Wealthy en MX").
- get_trend: serie temporal de una zona o agregado ("evolución de X en Chapinero").
- aggregate_metric: promediar/agregar por dimensión ("promedio de X por país").
- cross_metric_analysis: zonas con métrica A alta y métrica B baja (análisis multivariable).
- growth_analysis: zonas que más crecen en órdenes + drivers para hipótesis.
- get_schema_info: catálogo y cobertura de datos.
- resolve_zone: resolver el nombre real de una zona/ciudad ambigua antes de filtrar.

# Cómo trabajas
1. Identifica métrica(s), filtros, dimensión y ventana temporal. Si la zona es ambigua,
   usa resolve_zone primero.
2. Llama a la herramienta adecuada con parámetros precisos.
3. Si la herramienta devuelve {{"error": ...}} o {{"clarification_needed": ...}}, corrige los
   parámetros usando las "suggestions" y reintenta; si de verdad falta info, pídela al usuario.
4. Narra el resultado en **español**, claro y orientado a negocio. Cita solo números del JSON.
5. Respeta la dirección de cada métrica (higher_is_better): para métricas de costo como
   "Restaurants Markdowns / GMV", más alto = peor.
6. Si el resultado trae "quality_warning" o un caveat de calidad, MENCIÓNALO explícitamente
   (ej: zonas excluidas por valores fuera de rango). La honestidad de los datos es parte del valor.
7. Cierra SIEMPRE con 1–2 sugerencias proactivas de análisis relacionado, concretas y accionables.

# Interpretación de negocio
- "zonas problemáticas" → usa la definición del catálogo (deterioro WoW, tendencia negativa, GP UE
  negativo o Perfect Orders bajo). "zonas similares" → mismo país y mismo ZONE_TYPE.
- No afirmes causalidad: en growth_analysis los drivers son hipótesis ("podría explicarse por…"),
  no causas demostradas.

No describas tu proceso interno ni menciones "herramientas/JSON" al usuario: responde como un
analista de negocio que ya tiene los datos. Sé conciso; no inventes contexto que no esté en los datos."""


# ============================================================ tool schemas
_FILTERS = {
    "type": "object",
    "description": "Filtros geográficos/segmento. Todos opcionales.",
    "properties": {
        "country": {"type": "string", "enum": VALID_COUNTRIES, "description": "Código de país"},
        "city": {"type": "string"},
        "zone": {"type": "string"},
        "zone_type": {"type": "string", "enum": ["Wealthy", "Non Wealthy"]},
        "zone_prioritization": {
            "type": "string",
            "enum": ["High Priority", "Prioritized", "Not Prioritized"],
        },
    },
}
_WEEK = {"type": "integer", "minimum": -8, "maximum": 0, "description": "Semana: -8..0 (0 = actual)"}

TOOLS: list[dict] = [
    {
        "name": "query_metrics",
        "description": "Filtra y rankea zonas por una métrica en una semana. Úsala para "
        "'¿cuáles son las N zonas con mayor/menor X?'. ascending=true para las peores.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {"type": "string", "description": "Nombre de la métrica (acepta aliases)"},
                "filters": _FILTERS,
                "week": _WEEK,
                "top_n": {"type": "integer", "default": 10},
                "ascending": {"type": "boolean", "description": "true = menores valores primero"},
                "min_orders": {"type": "integer", "description": "Mínimo de órdenes en la semana"},
                "exclude_flagged": {"type": "boolean", "default": True},
            },
            "required": ["metric"],
        },
    },
    {
        "name": "compare_segments",
        "description": "Compara una métrica entre los segmentos de una dimensión. Úsala para "
        "'compara X entre Wealthy y Non Wealthy en MX' o 'X por tipo de zona'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {"type": "string"},
                "dimension": {
                    "type": "string",
                    "enum": ["ZONE_TYPE", "ZONE_PRIORITIZATION", "COUNTRY", "CITY"],
                },
                "filters": _FILTERS,
                "week": _WEEK,
            },
            "required": ["metric", "dimension"],
        },
    },
    {
        "name": "get_trend",
        "description": "Serie temporal de una métrica para UNA zona (o agregado). Úsala para "
        "'evolución/tendencia de X en <zona> últimas N semanas'. Acepta metric='Orders'. "
        "Si varias zonas coinciden y aggregate=false, pide aclaración.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {"type": "string"},
                "filters": _FILTERS,
                "weeks": {"type": "integer", "default": 8, "minimum": 1, "maximum": 8},
                "aggregate": {"type": "boolean", "description": "Promediar si hay varias zonas"},
            },
            "required": ["metric"],
        },
    },
    {
        "name": "aggregate_metric",
        "description": "Agrega (promedio simple o ponderado por órdenes) una métrica por dimensión. "
        "Úsala para '¿cuál es el promedio de X por país/tipo de zona?'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {"type": "string"},
                "group_by": {
                    "type": "string",
                    "enum": ["COUNTRY", "CITY", "ZONE_TYPE", "ZONE_PRIORITIZATION"],
                },
                "filters": _FILTERS,
                "week": _WEEK,
                "weighted_by_orders": {"type": "boolean", "default": False},
                "exclude_flagged": {"type": "boolean", "default": True},
            },
            "required": ["metric", "group_by"],
        },
    },
    {
        "name": "cross_metric_analysis",
        "description": "Encuentra zonas con metric_high ALTA y metric_low BAJA (cuartiles). Úsala "
        "para análisis multivariable: '¿qué zonas tienen alto X pero bajo Y?'. Devuelve correlación.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric_high": {"type": "string"},
                "metric_low": {"type": "string"},
                "filters": _FILTERS,
                "week": _WEEK,
                "quantile": {"type": "number", "default": 0.25},
                "top_n": {"type": "integer", "default": 15},
            },
            "required": ["metric_high", "metric_low"],
        },
    },
    {
        "name": "growth_analysis",
        "description": "Zonas con mayor crecimiento en órdenes en una ventana, con el cambio de "
        "métricas driver como hipótesis (no causalidad). Úsala para '¿qué zonas crecen más y por qué?'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filters": _FILTERS,
                "weeks": {"type": "integer", "default": 5, "minimum": 2, "maximum": 8},
                "top_n": {"type": "integer", "default": 10},
                "min_orders_base": {
                    "type": "integer",
                    "default": 500,
                    "description": "Base mínima de órdenes para evitar % explosivos en zonas chicas",
                },
            },
        },
    },
    {
        "name": "get_schema_info",
        "description": "Devuelve el catálogo de métricas, dimensiones, conceptos de negocio y "
        "cobertura de datos. Úsala si no estás seguro de qué métrica o dimensión existe.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "resolve_zone",
        "description": "Resuelve un texto libre a zonas reales (fuzzy). Úsala ANTES de filtrar por "
        "una zona cuyo nombre exacto no conoces, o si una herramienta pide aclarar la zona.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "country": {"type": "string", "enum": VALID_COUNTRIES},
            },
            "required": ["text"],
        },
    },
]


# ============================================================ tool dispatch
def dispatch_tool(name: str, args: dict | None) -> dict:
    """Ejecuta una herramienta del query_engine. Errores → dict estructurado (self-healing)."""
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return {"error": f"Herramienta desconocida: {name}"}
    try:
        out = fn(**(args or {}))
        return out if isinstance(out, dict) else {"result": out}
    except TypeError as e:
        return {"error": f"Parámetros inválidos para {name}: {e}"}
    except Exception as e:  # noqa: BLE001 — todo error vuelve al modelo para que se corrija
        return {"error": f"{type(e).__name__}: {e}"}


# ============================================================ visual extraction
def _meta(result: dict) -> dict:
    return {k: result[k] for k in ("metric", "format", "higher_is_better") if k in result}


def _table(title: str, rows: list[dict], meta: dict | None = None) -> dict:
    cols = list(rows[0].keys())
    return {
        "type": "table",
        "title": title,
        "columns": cols,
        "rows": [[r.get(c) for c in cols] for r in rows],
        "meta": meta or {},
    }


def result_to_events(name: str, result: dict) -> list[dict]:
    """Construye eventos de visualización deterministas desde el resultado de una herramienta.
    El LLM nunca toca estos datos: vienen directo del cálculo de pandas."""
    if not isinstance(result, dict) or "error" in result or "clarification_needed" in result:
        return []
    ev: list[dict] = []
    meta = _meta(result)

    if name == "query_metrics" and result.get("results"):
        rows = result["results"]
        ev.append(
            {
                "type": "chart",
                "kind": "bar",
                "title": f"{result.get('metric', '')} — top {len(rows)}",
                "xKey": "ZONE",
                "yKey": "VALUE",
                "data": [{"ZONE": r["ZONE"], "VALUE": r["VALUE"], "COUNTRY": r["COUNTRY"]} for r in rows],
                "meta": meta,
            }
        )
        ev.append(_table(f"{result.get('metric', '')} por zona", rows, meta))

    elif name == "compare_segments" and result.get("segments"):
        segs = result["segments"]
        ev.append(
            {
                "type": "chart",
                "kind": "bar",
                "title": f"{result.get('metric', '')} por {result.get('dimension', '')}",
                "xKey": "segment",
                "yKey": "mean",
                "data": [{"segment": k, "mean": v.get("mean"), "count": v.get("count")} for k, v in segs.items()],
                "meta": meta,
            }
        )
        ev.append(
            _table(
                f"{result.get('metric', '')} por {result.get('dimension', '')}",
                [{"segment": k, **v} for k, v in segs.items()],
                meta,
            )
        )

    elif name == "get_trend" and result.get("series"):
        ev.append(
            {
                "type": "chart",
                "kind": "line",
                "title": result.get("metric", "Tendencia"),
                "xKey": "week",
                "yKey": "value",
                "data": result["series"],
                "meta": meta,
            }
        )

    elif name == "aggregate_metric" and result.get("results"):
        rows = result["results"]
        ykey = "value" if "value" in rows[0] else "mean"
        ev.append(
            {
                "type": "chart",
                "kind": "bar",
                "title": f"{result.get('metric', '')} por {result.get('group_by', '')}",
                "xKey": "segment",
                "yKey": ykey,
                "data": rows,
                "meta": meta,
            }
        )
        ev.append(_table(f"{result.get('metric', '')} por {result.get('group_by', '')}", rows, meta))

    elif name == "cross_metric_analysis" and result.get("results"):
        rows = result["results"]
        mh, ml = result.get("metric_high"), result.get("metric_low")
        ev.append(
            {
                "type": "chart",
                "kind": "scatter",
                "title": f"{mh} (alto) vs {ml} (bajo)",
                "xKey": mh,
                "yKey": ml,
                "data": rows,
                "meta": {"spearman": result.get("spearman_correlation")},
            }
        )
        ev.append(_table(f"{mh} alto / {ml} bajo", rows))

    elif name == "growth_analysis" and result.get("top_growing_zones"):
        rows = result["top_growing_zones"]
        ev.append(
            {
                "type": "chart",
                "kind": "bar",
                "title": "Crecimiento de órdenes (%)",
                "xKey": "ZONE",
                "yKey": "GROWTH_PCT",
                "data": rows,
                "meta": {"format": "percent_points"},
            }
        )
        ev.append(_table("Zonas de mayor crecimiento", rows))

    return ev


# ============================================================ streaming loop
_SYSTEM_BLOCKS = [
    {"type": "text", "text": build_system_prompt(), "cache_control": {"type": "ephemeral"}}
]


async def stream_agent(
    messages: list[dict], *, model: str | None = None
) -> AsyncIterator[dict]:
    """Loop de tool use con streaming. Yields eventos:
      {"type": "token", "text": ...}          fragmento de narración
      {"type": "tool", "name", "input"?, "status": "running"|"done"}
      {"type": "table"|"chart", ...}          visualizaciones deterministas
      {"type": "done", "messages": [...], "assistant_text": ..., "usage": {...}}
      {"type": "error", "message": ...}
    `messages` se extiende con los turnos del asistente y los tool_result; el evento final
    'done' devuelve la lista completa para persistir como memoria conversacional.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        yield {
            "type": "error",
            "message": "Falta ANTHROPIC_API_KEY. Copia backend/.env.example a backend/.env y agrega tu clave.",
        }
        return

    model = model or DEFAULT_MODEL
    convo: list[dict] = list(messages)
    answer_parts: list[str] = []
    usage = {"input_tokens": 0, "output_tokens": 0}

    try:
        client = anthropic.AsyncAnthropic()
        for _ in range(MAX_ITERS):
            turn_text: list[str] = []
            async with client.messages.stream(
                model=model,
                max_tokens=MAX_TOKENS,
                temperature=0,
                system=_SYSTEM_BLOCKS,
                tools=TOOLS,
                messages=convo,
            ) as stream:
                async for text in stream.text_stream:
                    turn_text.append(text)
                    yield {"type": "token", "text": text}
                msg = await stream.get_final_message()

            usage["input_tokens"] += msg.usage.input_tokens
            usage["output_tokens"] += msg.usage.output_tokens
            convo.append({"role": "assistant", "content": msg.content})

            tool_uses = [b for b in msg.content if b.type == "tool_use"]
            if msg.stop_reason != "tool_use" or not tool_uses:
                answer_parts.append("".join(turn_text))
                break

            tool_results = []
            for tu in tool_uses:
                yield {"type": "tool", "name": tu.name, "input": tu.input, "status": "running"}
                result = dispatch_tool(tu.name, tu.input)
                for vis in result_to_events(tu.name, result):
                    yield vis
                yield {"type": "tool", "name": tu.name, "status": "done"}
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )
            convo.append({"role": "user", "content": tool_results})

        yield {
            "type": "done",
            "messages": convo,
            "assistant_text": "".join(answer_parts).strip(),
            "usage": usage,
        }
    except anthropic.APIError as e:
        yield {"type": "error", "message": f"Error de la API de Claude: {getattr(e, 'message', str(e))}"}
    except Exception as e:  # noqa: BLE001
        yield {"type": "error", "message": f"{type(e).__name__}: {e}"}
