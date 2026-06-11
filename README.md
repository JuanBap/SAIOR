# SAIOR — Sistema de Análisis Inteligente de Operaciones Rappi

Bot conversacional de datos + sistema de insights automáticos sobre las métricas
operacionales de **980 zonas en 9 países** de LATAM (últimas 8 semanas).
Solución al caso técnico de AI Engineer ([enunciado](enunciado.md)).

**Principio rector: el LLM nunca calcula. Traduce, orquesta y narra — Python calcula.**
La única tarea probabilística del sistema es traducir la pregunta en lenguaje natural a una
llamada de función tipada; todo número que ves proviene de pandas, y por eso es testeable.

```
┌──────────────────────────────┐      SSE       ┌─────────────────────────────────┐
│  frontend/  Next.js 16       │ ◀────────────  │  backend/  FastAPI              │
│  · Chat con streaming        │   POST /chat   │  · agent.py — loop de tool use  │
│  · Gráficos Recharts         │                │    (Claude Sonnet 4.6, temp 0)  │
│  · /insights dashboard       │  GET /insights │  · query_engine.py — 8 tools    │
│  · Export CSV / MD / PDF     │ ────────────▶  │    deterministas (pydantic)     │
└──────────────────────────────┘                │  · insights/ — detectores       │
                                                │    estadísticos + reporte       │
                                                │  · parquet tidy + catálogo      │
                                                │    semántico (13 métricas)      │
                                                └─────────────────────────────────┘
```

---

## Inicio rápido

Requisitos: Python 3.12+, Node 20+ con `pnpm`, una API key de [Anthropic](https://console.anthropic.com/).

**1. Backend** (puerto 8000):

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # editar: ANTHROPIC_API_KEY=sk-ant-...
cd src && ../.venv/bin/uvicorn api:app --port 8000
```

**2. Frontend** (puerto 3000):

```bash
cd frontend
pnpm install
pnpm dev
```

Abrir **http://localhost:3000**. El punto verde "API" del header confirma la conexión.
Los datos procesados (parquet) vienen incluidos: no se necesita el Excel original para correr.

---

## Qué hace

### 🤖 Bot conversacional (`/`)

Responde en lenguaje natural sobre las 13 métricas del catálogo. Los 6 tipos de query del
caso están como tarjetas clickeables en la pantalla inicial:

| Tipo | Ejemplo | Herramienta que orquesta |
|---|---|---|
| Filtrado | "5 zonas con mayor Lead Penetration esta semana" | `query_metrics` |
| Comparación | "Perfect Order: Wealthy vs Non Wealthy en México" | `compare_segments` |
| Tendencia | "evolución de Gross Profit UE en Chapinero" | `get_trend` (+`resolve_zone`) |
| Agregación | "promedio de Lead Penetration por país" | `aggregate_metric` |
| Multivariable | "alto Lead Penetration pero bajo Perfect Order" | `cross_metric_analysis` |
| Inferencia | "qué zonas crecen más y qué lo explica" | `growth_analysis` |

Además: **memoria conversacional** por sesión (los follow-ups resuelven contexto), conceptos
de negocio ("zonas problemáticas" tiene definición operativa en el catálogo), **sugerencias
proactivas** al final de cada respuesta, y advertencias de calidad de datos cuando aplican.

Cada consulta del agente renderiza un **gráfico determinista** (construido en Python desde el
resultado real, nunca por el LLM) y una **tabla expandible con export CSV**. Bajo cada
respuesta se muestra el costo real de la consulta.

### 📊 Insights automáticos (`/insights`)

Detección estadística pura (sin LLM en el cálculo) sobre todo el portafolio:

- **Anomalías** — cambios WoW > ±10% (con piso de base para evitar % sobre ~0)
- **Tendencias preocupantes** — deterioro 3+ semanas consecutivas (dirección por catálogo)
- **Benchmarking** — zonas >1.5σ bajo su peer group (mismo país + tipo de zona)
- **Oportunidades** — zonas High Priority bajo la mediana de sus peers
- **Correlaciones** — Spearman entre métricas (GP UE winsorizado p1/p99)
- **Calidad de datos** — zonas con valores fuera de rango, como sección propia

Los hallazgos se priorizan por **impacto ponderado por volumen de órdenes**
(`impact = severidad × (1 + ln(1 + órdenes))`): una caída de 15% en una zona de 20k órdenes
importa más que en una de 200. El reporte sale como dashboard navegable, heatmap país×métrica,
**Markdown descargable**, **PDF** (imprimir) y una **síntesis ejecutiva redactada por Claude**
exclusivamente a partir de los números ya calculados.

---

## Precisión: medida, no afirmada

Dos suites cubren las dos mitades del sistema:

```bash
cd backend
.venv/bin/python -m pytest tests/ -v          # 13 tests, <2s, sin API key
.venv/bin/python scripts/run_golden_live.py   # 8 casos por el agente real (~$0.17)
```

- **`tests/test_golden_queries.py`** — regresión determinista: los 6 casos del brief con
  valores congelados, resolución de aliases en español, self-healing de errores e
  invariantes de calidad (ningún valor `OK` puede violar el `valid_range` del catálogo).
- **`scripts/run_golden_live.py`** — valida la única parte probabilística (traducción
  NL→herramienta) pasando las preguntas reales por Claude: herramienta esperada, parámetros
  clave, visualizaciones y términos ancla. Última corrida: **8/8 PASS, $0.17 USD**.

## Costos de API (Claude Sonnet 4.6)

| Operación | Costo medido |
|---|---|
| Primera pregunta de una sesión (escribe el caché del system prompt) | ~$0.03 |
| Preguntas siguientes (caché activo) | ~$0.013–0.022 |
| **Sesión de 10 preguntas** | **~$0.15–0.20** |
| Síntesis ejecutiva del reporte de insights | ~$0.01 |
| Suite golden en vivo completa (8 preguntas) | ~$0.17 |

Tarifas: $3 input / $15 output / $0.30 cache-read / $3.75 cache-write por millón de tokens.
El system prompt (~4.8k tokens con catálogo y herramientas) se cachea con `cache_control`.

---

## Datos y reproducibilidad

`backend/data/processed/` (parquet tidy, incluido en el repo) se genera desde el Excel
original con:

```bash
cd backend
.venv/bin/python src/prepare_data.py data/raw/<archivo>.xlsx   # ingesta completa
.venv/bin/python src/prepare_data.py --reflag                  # recalcular solo flags
```

La ingesta deduplica (Gross Profit UE venía duplicado exacto), normaliza a formato largo
(zona × métrica × semana, WEEK ∈ [-8, 0]) y marca `OUT_OF_RANGE` todo valor fuera del
`valid_range` declarado en `metrics_catalog.json` — la capa semántica es la única fuente de
verdad de validación (32 zonas de Lead Penetration con ratios imposibles >100% quedan
excluidas de los rankings por defecto y reportadas como insight de calidad).

## Estructura

```
├── enunciado.md                  # brief del caso
├── backend/
│   ├── src/
│   │   ├── prepare_data.py       # ingesta: dedupe, tidy, flags por catálogo
│   │   ├── metrics_catalog.json  # capa semántica: 13 métricas, aliases ES, rangos, conceptos
│   │   ├── query_engine.py       # 8 herramientas deterministas (pydantic)
│   │   ├── agent.py              # loop de tool use Claude + system prompt + visuales SSE
│   │   ├── api.py                # FastAPI: /chat (SSE), /insights, /export/csv, /health
│   │   └── insights/             # detectores estadísticos + reporte ejecutivo
│   ├── tests/                    # golden suite (pytest)
│   ├── scripts/run_golden_live.py
│   └── data/{raw,processed}/
├── frontend/                     # Next.js 16 + Tailwind v4 + shadcn/ui + Recharts
│   └── src/{app,components,lib}/
└── docs/ARCHITECTURE.md          # decisiones técnicas, defensas de precisión, trade-offs
```

## Decisiones, límites y siguientes pasos

Las decisiones de arquitectura (por qué tool-use tipado y no text-to-SQL, por qué código y no
n8n/Zapier, las 7 defensas contra el no-determinismo) están en
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Limitaciones conocidas** — y qué haría con más tiempo:

- La memoria conversacional vive en el proceso (dict): suficiente para demo; en producción
  iría a Redis con TTL.
- Los hallazgos críticos del insights engine los domina Gross Profit UE (sus variaciones en
  moneda superan a los ratios acotados 0–1): una mejora natural es normalizar la severidad
  por la volatilidad histórica de cada métrica.
- El dataset es estático (8 semanas): el diseño tidy + catálogo soporta ingesta incremental
  semanal sin cambios en el engine.
- Sin autenticación ni rate-limiting: fuera del alcance del caso.
