# DROPOFF — Sistema de Análisis Inteligente para Operaciones Rappi

> Documento de traspaso de contexto. Leer completo antes de escribir código.
> Estado al 2026-06-10. Fases 1 y 2 completadas y verificadas.

---

## 1. Qué es este proyecto

Prueba técnica para rol **AI Engineer en Rappi**. Plazo: **2 días calendario** desde recepción de datos. Entrega: repo Git público + **demo en vivo** de 30 min (20 presentación + 10 Q&A).

**Misión del caso:** sistema de IA que democratice acceso a métricas operacionales de 980 zonas en 9 países LATAM y automatice generación de insights.

### Entregables y rúbrica (100 pts)

| Entregable | Peso interno | Criterio rúbrica | Peso |
|---|---|---|---|
| **2.1 Bot conversacional de datos** | 70% del caso | Calidad del Bot (precisión, queries complejas, UX) | 35% |
| **2.2 Sistema de insights automáticos** | 30% del caso | Calidad de Insights (relevancia, accionabilidad) | 30% |
| | | Presentación y comunicación | 20% |
| | | Arquitectura y diseño técnico | 15% |
| | | Código y documentación | 5% |

### Los 6 casos de uso OBLIGATORIOS del bot (ya cubiertos por el engine, ver §4)

1. Filtrado: "¿Cuáles son las 5 zonas con mayor % Lead Penetration esta semana?"
2. Comparaciones: "Compara el Perfect Order entre zonas Wealthy y Non Wealthy en México"
3. Tendencias: "Muestra la evolución de Gross Profit UE en Chapinero últimas 8 semanas"
4. Agregaciones: "¿Cuál es el promedio de Lead Penetration por país?"
5. Multivariable: "¿Qué zonas tienen alto Lead Penetration pero bajo Perfect Order?"
6. Inferencia: "¿Cuáles zonas crecen más en órdenes en las últimas 5 semanas y qué podría explicarlo?"

Requisitos adicionales del bot: manejo de contexto de negocio ("zonas problemáticas" → inferir métricas deterioradas), **sugerencias proactivas** de análisis, **memoria conversacional**.

Requisitos del sistema de insights (mínimo): anomalías (cambios >±10% WoW), tendencias preocupantes (3+ semanas de deterioro), benchmarking de zonas similares (mismo país/tipo), correlaciones entre métricas, oportunidades. Reporte ejecutivo: resumen top 3-5 hallazgos críticos + detalle por categoría + recomendación accionable por hallazgo.

Bonus elegidos por el usuario: **gráficos**, **export CSV/PDF**, **deploy en la nube**. (Email automático: descartado.)

---

## 2. Decisiones de arquitectura YA TOMADAS (no reabrir)

| Decisión | Elección | Justificación (para defensa en Q&A) |
|---|---|---|
| Principio rector | **El LLM nunca calcula: traduce, orquesta y narra. Python calcula.** | Convierte un sistema no determinista en precisión determinista |
| LLM | **Claude (Anthropic API)** — usuario TIENE api key con créditos | Tool use robusto, español, costo ~$0.02–0.06/sesión de 10 preguntas con Sonnet |
| Backend | **FastAPI (Python)**: agente + query engine pandas + insights | pandas testeable con pytest; el agente vive donde viven los datos |
| Frontend | **Next.js + React + shadcn/ui** | Fortaleza del usuario (ya desplegó apps Next.js/Supabase reales); diferenciación visual |
| Gráficos | **Recharts por defecto** (nativo shadcn); **Plotly.js SOLO para heatmap** de benchmarking en /insights | Regla explícita acordada, no mezclar arbitrariamente |
| Insights UI | Página **/insights** en la app + **export PDF** | Dashboard navegable en demo + documento entregable |
| Deploy | **Vercel** (frontend) + **Railway o Render** (FastAPI) | Free tiers, bonus de la rúbrica |
| Temperature | **0** en todas las llamadas | Defensa #6 contra no-determinismo |

### Las 7 defensas contra el no-determinismo (núcleo de la narrativa de presentación)

1. Tool use con schemas pydantic — el LLM solo emite JSON validado, nunca toca datos
2. Catálogo semántico en system prompt (13 métricas: definición, dirección, aliases ES, caveats)
3. Resolución de entidades determinista en Python (fuzzy match de zonas, no el LLM)
4. Self-healing loop: error estructurado → el LLM corrige parámetros (máx 2 reintentos)
5. Narración anclada: el LLM redacta SOLO desde el JSON de resultados reales
6. Temperature = 0
7. Golden test set: los 6 casos del brief con respuestas verificadas → suite de regresión pytest. Frase para el Q&A: "la precisión no la afirmo, la mido"

---

## 3. Los datos: hallazgos críticos del perfilado (mencionar en presentación)

Fuente: Excel con hojas RAW_INPUT_METRICS (12,573 filas) y RAW_ORDERS (1,242 filas).
9 países (AR,BR,CL,CO,CR,EC,MX,PE,UY), 270 ciudades, 980 zonas, 13 métricas, semanas L8W→L0W.

1. **Gross Profit UE viene duplicado exacto** (963 filas, valores idénticos) → dedupe en ingesta (HECHO en `prepare_data.py`)
2. **Lead Penetration: 32 zonas con valores imposibles** (ratio >1, hasta 393.9, concentradas en Quito/Guayaquil) → flag `OUT_OF_RANGE` (HECHO); las herramientas excluyen flags por defecto con `exclude_flagged=True` y lo declaran en la respuesta
3. **Nulos crecientes hacia el pasado** (113 en L8W → 0 en L0W): zonas nuevas → tendencias exigen mínimo de semanas válidas
4. **Turbo Adoption solo en 285/980 zonas** → ausencia ≠ mal desempeño (caveat en catálogo)
5. **Orders (1,242 zonas) ∩ Métricas (980) = 978** → joins inner con nota de cobertura
6. **GP UE con outliers extremos** (hasta -97/orden) → winsorizar en correlaciones del insights engine
7. Semántica de WEEK: entero -8..0, donde 0 = semana actual. "últimas 5 semanas" = -4..0

Resultados verificados de referencia (para validar que nada se rompa):
- Perfect Orders MX: Wealthy mean 0.9043 (n=74), Non Wealthy mean 0.8666 (n=228), gap -3.8pp
- GP UE Chapinero (CO/Bogota): serie -8→0 = 2.90→2.99, pico 3.45 en L1W, caída en L0W
- Lead Penetration por país (flags excluidos): EC=0.1662, CO=0.5436, PE=0.9189
- Top growth 5 semanas (base ≥500 órdenes): Centro de Cuenca EC +46.9%, Sabaneta CO +37.4%
- Spearman Lead Penetration vs Perfect Orders: 0.309

---

## 4. Estado actual del código (TODO PROBADO Y FUNCIONANDO)

```
rappi-ai/
├── docs/ARCHITECTURE.md          # diagrama, decisiones, plan 48h (v1: dice Streamlit;
│                                 #   ACTUALIZAR a Next.js+FastAPI — única deuda)
├── src/
│   ├── prepare_data.py           # ✅ ingesta: dedupe, tidy, flags. CLI: python src/prepare_data.py <xlsx|dir>
│   ├── metrics_catalog.json      # ✅ capa semántica: 13 métricas + dimensiones + conceptos de negocio
│   │                             #    ("zona problemática", "zonas similares" = mismo COUNTRY+ZONE_TYPE, etc.)
│   └── query_engine.py           # ✅ 8 herramientas deterministas + pydantic + TOOL_REGISTRY
└── data/processed/               # ✅ parquet: metrics_long, orders_long, metrics_wide, orders_wide
```

### API del query engine (firma exacta — el agente la expone como tools de Anthropic)

- `query_metrics(metric, filters?, week=0, top_n=10, ascending=False, min_orders?, exclude_flagged=True)`
- `compare_segments(metric, dimension, filters?, week=0)` — dimension ∈ {ZONE_TYPE, ZONE_PRIORITIZATION, COUNTRY, CITY}
- `get_trend(metric, filters?, weeks=8, aggregate=False)` — acepta "Orders"; si >1 zona y no aggregate → pide clarificación
- `aggregate_metric(metric, group_by, filters?, week=0, weighted_by_orders=False, exclude_flagged=True)`
- `cross_metric_analysis(metric_high, metric_low, filters?, week=0, quantile=0.25, top_n=15)`
- `growth_analysis(filters?, weeks=5, top_n=10, min_orders_base=500)` — incluye deltas de métricas driver (hipótesis, no causalidad)
- `get_schema_info()` — catálogo + cobertura
- `resolve_zone(text, country?)` — fuzzy, devuelve candidatos

`filters` = dict: {country (código), city, zone, zone_type, zone_prioritization}. Errores devuelven `{"error": ..., "suggestions": [...]}` — diseñados para el self-healing loop.

Dependencias instaladas hasta ahora: pandas, pyarrow, pydantic, openpyxl.

---

## 5. LO QUE FALTA — plan de trabajo en orden de prioridad

### Bloque A — Agente FastAPI (siguiente paso inmediato, ~3-4h) [Bot 35%]
- `src/agent.py`: loop de tool use con SDK `anthropic` (modelo claude-sonnet-4, temperature=0, max 2 reintentos por error de tool)
- System prompt debe incluir: catálogo semántico completo, conceptos de negocio, reglas: (a) nunca citar números que no estén en resultados de tools, (b) advertir flags de calidad, (c) responder en español, (d) terminar con 1-2 sugerencias proactivas de análisis relacionado, (e) "zonas problemáticas" → usar definición del catálogo
- `src/api.py`: FastAPI con POST /chat (streaming SSE), POST /export/csv, GET /insights, GET /insights/pdf
- Memoria conversacional: historial de mensajes por session_id (en memoria, dict; no sobre-ingeniar)
- **Protocolo chart-spec**: cuando una tool devuelve `chart_suggestion`, el agente emite bloque JSON `{type: "chart", chart: {kind: "line|bar|scatter", title, data: [...], xKey, yKey, series?}}` dentro del stream → frontend lo renderiza. Definir el contrato ANTES de tocar frontend
- `.env.example` con ANTHROPIC_API_KEY; documentar costo estimado por sesión en README (requisito explícito del brief)

### Bloque B — Frontend Next.js (~4-5h) [Bot UX + diferenciación]
- App Router, shadcn/ui, tema oscuro profesional tipo Rappi (naranja #FF441F como acento)
- Chat con streaming, render de chart-specs con Recharts, tabla de resultados con botón export CSV
- Chips de preguntas sugeridas (los 6 casos del brief como ejemplos clickeables — facilita la demo en vivo)
- Página /insights consumiendo GET /insights

### Bloque C — Insights engine (~3-4h) [Insights 30%]
- `src/insights/detectors.py`: anomalías WoW >±10% (L1W→L0W), tendencias 3+ semanas (usar dirección higher_is_better del catálogo), benchmarking peer-group (mismo COUNTRY+ZONE_TYPE, divergencia >1.5σ), correlaciones Spearman entre métricas (winsorizar GP UE al p1/p99), oportunidades (gap vs mediana de peers en zonas High Priority)
- **Ranking por impacto ponderado por volumen de órdenes** (caída de 15% en zona de 270k órdenes > zona de 200) — diferenciador clave del "balance técnico-negocio"
- `src/insights/report.py`: hallazgos rankeados → LLM redacta SOLO la narrativa (números ya calculados) → JSON para /insights + Markdown/PDF export
- Excluir QUALITY_FLAG != OK de todos los detectores; reportar problemas de calidad como sección propia del reporte (es un insight en sí mismo)

### Bloque D — Tests + docs (~2h) [Código 5% + defensa de precisión]
- `tests/test_golden_queries.py`: los 6 casos con los valores de referencia de §3
- README: setup, arquitectura, costos API, decisiones, limitaciones, instrucciones de ejecución (ambos servicios)

### Bloque E — Deploy + presentación (~3h) [Presentación 20%]
- Vercel + Railway/Render; CORS configurado; datos parquet incluidos en imagen del backend
- Guion de 20 min siguiendo estructura sugerida del brief: contexto/approach (3') → demo bot 5 preguntas en vivo (10') → insights (5') → decisiones técnicas (5') → limitaciones/next steps (2')
- Demo en vivo es OBLIGATORIA (no video). Tener localhost como fallback del deploy

---

## 6. Reglas de trabajo acordadas con el usuario

- Decisiones grandes se consultan; el usuario participa en la arquitectura (ya definió: Next.js+shadcn, FastAPI, Recharts+Plotly regla explícita, página+export para insights)
- Priorizar SIEMPRE por peso de rúbrica; bonus solo si lo obligatorio está sólido (FAQ del brief: "caso sólido sin bonus > bonus con implementación mediocre")
- El usuario presentará en español; código y comentarios pueden ser en español o inglés consistente
- Cada hallazgo de calidad de datos se resuelve POR DISEÑO (parámetros, flags), no por prompt
- Contacto del evaluador para dudas conceptuales: daniel.chain@rappi.com

## 7. Archivos de entrada originales

- Brief: `Caso_Técnico_Sistema_de_Análisis_Inteligente_para_Operaciones_Rappi.docx`
- Datos: Excel `Sistema_de_Análisis_Inteligente_para_Operaciones_Rappi_-_Dummy_Data.xlsx` (hojas RAW_INPUT_METRICS, RAW_ORDERS, RAW_SUMMARY). Colocar en `data/raw/` y correr `python src/prepare_data.py data/raw/<archivo>.xlsx` si hay que regenerar los parquet.
