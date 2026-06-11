# Arquitectura — SAIOR (Sistema de Análisis Inteligente de Operaciones Rappi)

**Principio rector: el LLM nunca calcula. El LLM traduce, orquesta y narra. Python calcula.**

Esto convierte un sistema no determinista en uno de **precisión determinista**: la única
tarea probabilística es la traducción de lenguaje natural a una llamada de función
estructurada — y esa traducción es verificable, validable y testeable (ver §4).

---

## 1. Diagrama

```
┌────────────────────────────────────────────────────────────────┐
│  FRONTEND — Next.js 16 (App Router) + Tailwind v4 + shadcn/ui  │
│  · Chat SSE con streaming token a token                        │
│  · Gráficos Recharts + tablas expandibles con export CSV       │
│  · /insights: dashboard + heatmap + Markdown/PDF + síntesis IA │
└───────────────────────────┬────────────────────────────────────┘
                            │ POST /chat (SSE) · GET /insights
┌───────────────────────────▼────────────────────────────────────┐
│  ORQUESTADOR (backend/src/agent.py)                            │
│  Claude Sonnet 4.6 + tool use · temperature 0                  │
│  · System prompt = catálogo semántico + conceptos de negocio   │
│    + reglas de honestidad y estilo (cacheado: cache_control)   │
│  · Memoria conversacional por session_id (incluye tool calls)  │
│  · Self-healing: el error estructurado vuelve al modelo        │
│  · Las visualizaciones NO las emite el LLM: se construyen en   │
│    Python desde el resultado real de cada tool (SSE aparte)    │
└───────────────────────────┬────────────────────────────────────┘
                            │ llamadas tipadas (JSON Schema)
┌───────────────────────────▼────────────────────────────────────┐
│  QUERY ENGINE (backend/src/query_engine.py) — determinista     │
│  query_metrics · compare_segments · get_trend ·                │
│  aggregate_metric · cross_metric_analysis · growth_analysis ·  │
│  get_schema_info · resolve_zone                                │
│  Validación pydantic → error estructurado con sugerencias      │
└───────────────────────────┬────────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────────────┐
│  CAPA DE DATOS                                                 │
│  parquet tidy (zona × métrica × semana) + metrics_catalog.json │
│  (13 métricas: definición, dirección, aliases ES, valid_range) │
│  Flags OUT_OF_RANGE derivados del catálogo en la ingesta       │
└────────────────────────────────────────────────────────────────┘

  En paralelo, sin LLM en el cálculo:
┌────────────────────────────────────────────────────────────────┐
│  INSIGHTS ENGINE (backend/src/insights/)                       │
│  Detectores: anomalías WoW ±10% · tendencias 3+ semanas ·      │
│  benchmark peers >1.5σ · oportunidades High Priority ·         │
│  correlaciones Spearman · calidad de datos                     │
│  → ranking por impacto ponderado por órdenes →                 │
│  → JSON / Markdown / heatmap; el LLM SOLO redacta la síntesis  │
└────────────────────────────────────────────────────────────────┘
```

## 2. Las 7 defensas contra el no-determinismo

| # | Defensa | Qué elimina |
|---|---------|-------------|
| 1 | **Tool use con schemas estrictos** (pydantic + JSON Schema con enums/rangos): el LLM solo puede emitir parámetros válidos | Acceso libre del LLM a los datos |
| 2 | **Catálogo semántico** en el system prompt: definición, dirección (`higher_is_better`), aliases en español y caveats por métrica | Ambigüedad de interpretación ("rentabilidad" → Gross Profit UE, siempre) |
| 3 | **Resolución de entidades en Python** (`resolve_metric`/`resolve_zone`, fuzzy determinista) | Nombres de zonas/métricas inventados |
| 4 | **Self-healing loop**: parámetros inválidos → error estructurado con `suggestions` → el modelo corrige (tope de iteraciones) | Fallos de traducción terminales |
| 5 | **Narración anclada + visuales deterministas**: el LLM redacta solo desde el JSON de resultados; gráficos y tablas los construye Python desde ese mismo JSON | Números o gráficos fabricados |
| 6 | **temperature = 0** | Varianza de traducción |
| 7 | **Golden test set en dos niveles**: pytest congela los 6 casos del brief contra el engine; un runner en vivo pasa las preguntas reales por el agente y valida herramienta + parámetros + anclas (última corrida: 8/8 PASS, $0.17) | Precisión afirmada sin evidencia |

> Defensa transversal: **la calidad de datos se resuelve por diseño, no por prompt**. Los
> flags `OUT_OF_RANGE` se derivan del `valid_range` del catálogo en la ingesta (un Lead
> Penetration de 110% es imposible por definición y jamás llega a un ranking).

## 3. Decisiones técnicas y justificación

| Decisión | Alternativa descartada | Justificación |
|----------|------------------------|---------------|
| **Tool use estructurado** | Text-to-SQL / text-to-pandas libre | Código generado libre es inauditable; herramientas tipadas acotan el espacio de error y son testeables unitariamente |
| **Claude Sonnet 4.6** | Opus (5× costo), Haiku (menos robusto multivariable) | Mejor balance para tool-use + narración en español; ~$0.15–0.20 por sesión de 10 preguntas |
| **FastAPI + SSE** | WebSockets / polling | Streaming token a token con un protocolo simple; los eventos `chart`/`table` viajan junto a los `token` |
| **Next.js + shadcn/ui** | Streamlit / Gradio | UX de producto (streaming, tema propio, tablas expandibles) y diferenciación en la demo; Streamlit acopla UI y cómputo en un solo proceso |
| **Recharts** | Plotly | Nativo de React, liviano; un solo lib de charts en todo el front |
| **Parquet tidy** | CSV crudo por query | Todo es un groupby/filter trivial; tipos preservados; carga en ms con `lru_cache` |
| **Insights sin LLM en el cálculo** | LLM "analizando" datos crudos | Detección estadística reproducible y defendible; el LLM solo aporta prosa ejecutiva |
| **Impacto ponderado por órdenes** | Ranking por % de cambio puro | Una caída de 15% en una zona de 20k órdenes ≠ una de 200; es el balance técnico-negocio que pide el caso |
| **Tabla colapsada + narración breve** | Volcar tabla + gráfico + tabla en texto | El gráfico cuenta la historia, el detalle queda a un clic, el LLM aporta el "so what" — no repite datos |

## 4. Por qué código y no una plataforma no-code (n8n / Zapier / Make)

| Dimensión | SAIOR (código) | n8n / Zapier / Make |
|---|---|---|
| Precisión numérica | El LLM nunca toca los datos: llamadas tipadas + pandas + temp 0 + golden tests | El LLM-node recibe los datos en el prompt y los "lee": alucinación posible, no testeable |
| Queries complejas | 8 herramientas componibles + self-healing | Cada caso = rama manual del workflow; lo no previsto no tiene ruta |
| Memoria conversacional | Historial completo con tool calls por sesión | Buffers simples; el contexto de qué se consultó se pierde |
| Visualización + export | Charts deterministas + CSV + streaming SSE | Sin UI de chat propia; sin gráficos nativos |
| Testabilidad | pytest (13 tests, <2s) + runner en vivo | Probar = ejecutar el flujo a mano |
| Versionado | Git con diffs legibles y commits atómicos | Export JSON de workflows, review impracticable |
| Latencia | Un proceso, parquet en memoria (ms por consulta) | Hop HTTP por nodo + datos en Sheets/Airtable |
| Costo | ~$0.01–0.03 por consulta, directo al LLM | Plataforma + costo por ejecución/task + LLM |
| Datos sensibles | Nunca salen del backend propio | Cruzan la nube del vendor |
| Extensibilidad | Nueva capacidad = 1 función + 1 schema | Rediseño del workflow; vendor lock-in |

*Cuándo sí usaría no-code:* automatizaciones de integración simples ("si llega email,
postear en Slack"). Este caso pide precisión auditable sobre 104k filas, UX conversacional
con gráficos y un sistema de insights testeable — tres cosas cuya unidad de diseño es el
*dato*, no el *flujo*.

## 5. Hallazgos del perfilado de datos (resueltos por diseño)

1. **Gross Profit UE duplicado exacto** (~1.9k filas) → dedupe en la ingesta.
2. **Lead Penetration con ratios imposibles** (>100%, hasta 393.9; 32 zonas en la semana
   actual, concentradas en Ecuador) → flag `OUT_OF_RANGE` por `valid_range` del catálogo;
   excluidas por defecto y reportadas como insight de calidad propio.
3. **Nulos crecientes hacia el pasado** (zonas nuevas) → tendencias exigen semanas válidas.
4. **Turbo Adoption solo en 285/980 zonas** → caveat en catálogo: ausencia ≠ mal desempeño.
5. **Orders (1,242 zonas) ∩ métricas (980) = 978** → joins inner con nota de cobertura.
6. **GP UE con outliers extremos** (hasta -97/orden) → winsorización p1/p99 en correlaciones,
   benchmarking y heatmap (etiquetado `(winsor.)` cuando aplica, valor real preservado).
7. **% explosivos sobre bases ~0** en anomalías WoW → se exige base previa ≥10% del IQR.

## 6. Limitaciones y siguientes pasos

- **Memoria por proceso** (dict): demo-grade; producción → Redis con TTL por sesión.
- **Severidad dominada por GP UE** en hallazgos críticos (variaciones en moneda > ratios
  acotados): siguiente iteración → normalizar por volatilidad histórica de cada métrica.
- **Dataset estático**: el diseño tidy + catálogo admite ingesta incremental semanal y
  alertas programadas (el insights engine ya es un batch reutilizable).
- **Bonus pendientes por decisión**: deploy (Vercel + Railway/Render) y envío por email del
  reporte — descartado el segundo a favor de la página /insights + exportes.
