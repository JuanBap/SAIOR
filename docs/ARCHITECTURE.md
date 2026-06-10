# Arquitectura — Sistema de Análisis Inteligente para Operaciones Rappi

**Principio rector: el LLM nunca calcula. El LLM traduce, orquesta y narra. Python calcula.**

Esto convierte un sistema no determinista en uno de **precisión determinista**: la única
tarea probabilística es la traducción de lenguaje natural a una llamada de función
estructurada, y esa traducción es verificable, validable y testeable.

---

## 1. Diagrama de arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│  UI — Streamlit (chat + gráficos Plotly + export CSV)       │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  ORQUESTADOR (agent loop)                                   │
│  Claude API + Tool Use                                      │
│  · System prompt = contexto de negocio + catálogo semántico │
│  · Memoria conversacional (historial de mensajes)           │
│  · Decide qué herramienta llamar y con qué parámetros       │
└──────────────────────────┬──────────────────────────────────┘
                           │  tool calls (JSON validado)
┌──────────────────────────▼──────────────────────────────────┐
│  QUERY ENGINE (Python puro, determinista)                   │
│  Herramientas tipadas:                                      │
│  · query_metrics(filtros, agregación, top_n, semanas)       │
│  · compare_segments(métrica, dimensión, segmentos)          │
│  · get_trend(métrica, zona/agregado, ventana)               │
│  · cross_metric_analysis(métrica_a, métrica_b, umbrales)    │
│  · growth_analysis(ventana, top_n) [usa Orders]             │
│  · get_schema_info() / resolve_entity(texto)                │
│  Validación: pydantic — parámetros inválidos → error claro  │
│  que el LLM recibe y corrige (self-healing loop)            │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  CAPA DE DATOS                                              │
│  parquet tidy (metrics_long, orders_long) + catálogo        │
│  semántico (metrics_catalog.json) + flags de calidad        │
└─────────────────────────────────────────────────────────────┘

  Paralelo, sin LLM en el cálculo:
┌─────────────────────────────────────────────────────────────┐
│  INSIGHTS ENGINE (batch, 30% del peso)                      │
│  Detectores estadísticos puros:                             │
│  · Anomalías WoW (>±10%)        · Tendencias 3+ semanas     │
│  · Benchmarking peer-group      · Correlaciones (Spearman)  │
│  · Oportunidades (gaps vs. mediana de peers)                │
│  → JSON de hallazgos rankeados por impacto (ponderado por   │
│    volumen de órdenes) → LLM SOLO redacta el reporte        │
│    ejecutivo a partir de números ya calculados              │
└─────────────────────────────────────────────────────────────┘
```

## 2. Las 7 defensas contra el no-determinismo

| # | Defensa | Qué resuelve |
|---|---------|--------------|
| 1 | **Tool use con schema estricto** (pydantic): el LLM solo puede emitir JSON válido contra schemas tipados | Elimina alucinación de números — el LLM no tiene acceso libre a los datos |
| 2 | **Catálogo semántico** inyectado en el system prompt: 13 métricas con definición, dirección (higher_is_better), aliases, caveats | Elimina ambigüedad de interpretación ("rentabilidad" → Gross Profit UE, siempre) |
| 3 | **Resolución de entidades determinista**: fuzzy matching en Python (no en el LLM) para zonas/ciudades ("Chapinero" → CO/Bogota/Chapinero) | El LLM nunca inventa nombres de zonas |
| 4 | **Self-healing loop**: si los parámetros son inválidos, el engine devuelve error estructurado y el LLM reintenta (máx. 2) | Convierte fallos de traducción en correcciones automáticas |
| 5 | **Respuesta anclada a resultados**: el LLM redacta a partir del JSON de resultados reales devuelto por el engine; instrucción explícita de citar solo números presentes en el resultado | Cero números inventados en la narración |
| 6 | **Temperature = 0** + system prompt con reglas de formato y negocio | Reduce varianza de traducción |
| 7 | **Golden test set**: las 6 categorías de queries del brief + variantes, con respuesta esperada calculada a mano; suite de regresión ejecutable | Precisión demostrable y medible ante el evaluador (oro para el Q&A) |

## 3. Decisiones técnicas y justificación (15% de la rúbrica)

| Decisión | Alternativa descartada | Justificación |
|----------|------------------------|---------------|
| **Tool use estructurado** | Text-to-SQL / text-to-pandas libre | Código generado libremente es inauditable y frágil; herramientas tipadas acotan el espacio de error y son testeables |
| **Claude Sonnet** (claude-sonnet-4) | GPT-4 / open-source | Tool use nativo robusto, mejor seguimiento de instrucciones en español, costo ~$0.02–0.06 por sesión de 10 preguntas |
| **Streamlit** | Gradio / Flask custom | Chat UI nativa, gráficos Plotly integrados, deploy gratis en Streamlit Cloud, velocidad de desarrollo |
| **Parquet tidy** | CSV crudo en cada query | Formato largo = toda operación es un groupby/filter trivial; tipos preservados; 10x más rápido |
| **Insights sin LLM en el cálculo** | LLM analizando datos crudos | Detección estadística es determinista, reproducible y defendible; el LLM solo aporta redacción ejecutiva |
| **Impacto ponderado por órdenes** | Insights por % de cambio puro | Una caída de 15% en una zona de 270k órdenes importa más que en una de 200; esto es el "balance técnico-negocio" que piden |

## 4. Hallazgos del perfilado de datos (mencionar en la presentación — demuestra rigor)

1. **Gross Profit UE viene duplicado exactamente** (1,904 filas duplicadas, valores idénticos) → dedupe en ingesta. Detectarlo es un punto a favor.
2. **Lead Penetration tiene 32 zonas con valores imposibles** (>1, hasta 393.9, concentradas en Ecuador) → flag `OUT_OF_RANGE`; el bot lo advierte al reportar esas zonas.
3. **Nulos crecientes hacia semanas antiguas** (113 en L8W → 0 en L0W): zonas nuevas sin historia → los cálculos de tendencia exigen mínimo de semanas válidas.
4. **Turbo Adoption solo existe en 285/980 zonas** → ausencia ≠ mal desempeño; el catálogo lo documenta.
5. **Orders (1,242 zonas) y Métricas (980 zonas) cruzan en 978** → joins siempre inner con advertencia de cobertura.
6. **Gross Profit UE tiene outliers extremos** (hasta -97 por orden) → winsorización opcional en correlaciones para no distorsionar.

## 5. Estructura del repositorio

```
rappi-ai-analyst/
├── README.md                  # setup, arquitectura, costos, decisiones
├── requirements.txt
├── data/
│   ├── raw/                   # Excel/CSVs originales
│   └── processed/             # parquet tidy (generado por prepare_data.py)
├── src/
│   ├── prepare_data.py        # ingesta: dedupe, tidy, flags de calidad
│   ├── metrics_catalog.json   # capa semántica (la fuente de verdad)
│   ├── query_engine.py        # herramientas deterministas + pydantic
│   ├── agent.py               # orquestador Claude + tool use + memoria
│   ├── insights/
│   │   ├── detectors.py       # anomalías, tendencias, benchmark, correlaciones
│   │   └── report.py          # ranking por impacto + redacción LLM → MD/HTML
│   └── app.py                 # Streamlit: chat + gráficos + export
├── tests/
│   └── test_golden_queries.py # las 6 categorías del brief + edge cases
└── docs/
    └── ARCHITECTURE.md
```

## 6. Plan de 48 horas (priorizado por rúbrica)

| Bloque | Horas | Entregable | Peso cubierto |
|--------|-------|-----------|---------------|
| 1. Capa de datos + catálogo | 2 | ✅ ya hecho | base de todo |
| 2. Query engine + herramientas | 4 | 6 tools deterministas testeadas | Bot 35% |
| 3. Agente + system prompt | 3 | loop de tool use con memoria | Bot 35% |
| 4. UI Streamlit + gráficos | 3 | chat funcional con Plotly | Bot + UX |
| 5. Insights engine | 4 | detectores + reporte ejecutivo | Insights 30% |
| 6. Golden tests + README | 2 | suite de regresión + docs | Código 5% |
| 7. Guion de presentación + demo script | 2 | narrativa de 20 min + 5 queries demo | Presentación 20% |
| Buffer / pulido | 4 | edge cases, export CSV, deploy opcional | Atención al detalle |
