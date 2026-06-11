# SAIOR — Sistema de Análisis Inteligente de Operaciones Rappi

Bot conversacional de datos + sistema de insights automáticos sobre las métricas
operacionales de **980 zonas en 9 países** de LATAM. **Multiusuario**: login con Supabase
Auth y conversaciones persistentes que puedes continuar, renombrar o eliminar cuando quieras.
Solución al caso técnico de AI Engineer ([enunciado](enunciado.md)).

**Principio rector: el LLM nunca calcula. Traduce, orquesta y narra — los datos los consulta
Python/SQL.** La única tarea probabilística es traducir la pregunta a una consulta, y eso se
mide con dos suites de tests.

```
┌─────────────────────────────┐       JWT        ┌──────────────────────────────────┐
│ frontend/  Next.js 16       │ ───────────────▶ │ backend/  FastAPI (REST API)     │
│  /          landing pública │   POST /chat     │  valida JWT (JWKS) → user_id     │
│  /login     Supabase Auth   │   (SSE)          │  AGENTE Claude Sonnet 4.6 temp 0 │
│  /chat      sidebar + replay│  /conversations  │   ├ nivel 1: 8 tools verificados │
│  /insights  dashboard       │  /insights       │   │   (pandas sobre snapshot)    │
└─────────────────────────────┘                  │   └ nivel 2: run_sql con guardia │
                                                 │       AST + rol read-only        │
                                                 └────────────┬─────────────────────┘
                                                              │
                                       ┌──────────────────────▼──────────────────────┐
                                       │ SUPABASE (Postgres + Auth)                  │
                                       │  ops.*  datos del caso (104k filas)         │
                                       │  app.*  conversaciones · replay · query_log │
                                       │  auth   usuarios (email + contraseña)       │
                                       └─────────────────────────────────────────────┘
```

---

## Inicio rápido

Requisitos: Python 3.12+, Node 20+ con `pnpm`, una API key de
[Anthropic](https://console.anthropic.com/) y un proyecto de [Supabase](https://supabase.com).

**1. Backend** (puerto 8000):

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # completar: ANTHROPIC_API_KEY + credenciales de Supabase
.venv/bin/python scripts/apply_migrations.py   # schemas ops + app en tu Supabase
.venv/bin/python scripts/load_supabase.py      # carga el dataset (verifica goldens, ~5s)
.venv/bin/python scripts/seed_users.py         # usuarios demo: juan/mariana/daniel@saior.demo
cd src && ../.venv/bin/uvicorn api:app --port 8000
```

**2. Frontend** (puerto 3000):

```bash
cd frontend
pnpm install
cp .env.example .env.local    # URL del API + URL/anon key de Supabase
pnpm dev
```

Abrir **http://localhost:3000** → landing → Entrar (usuario demo o regístrate). El punto
verde "API" del header confirma la conexión; `/health` reporta si los datos vienen de
Supabase o del fallback parquet local (resiliencia de demo).

---

## Qué hace

### 🤖 Bot conversacional (`/chat`)

Responde en lenguaje natural sobre las 13 métricas del catálogo, con **motor de dos niveles**:

| Nivel | Cuándo | Garantía |
|---|---|---|
| **1 · Consultas verificadas** (8 herramientas tipadas) | Los 6 casos del brief y la gran mayoría de preguntas | Determinista, golden tests, badge ✓ |
| **2 · SQL generado** (`run_sql`) | Solo cuando ningún tool cubre la pregunta (medianas, percentiles, cortes nuevos) | Read-only + validación AST + LIMIT 500 + timeout 5s + **auditado en `app.query_log`**, badge 🧪 |

Cada respuesta declara su nivel con un badge — transparencia sobre la garantía, no un parche.
En ambos niveles **los números salen de la consulta, nunca del modelo**, y los gráficos/tablas
se construyen en Python desde el resultado real.

Además: **conversaciones persistentes por usuario** (recargar no pierde nada; un follow-up
del día siguiente conserva todo el contexto), memoria conversacional real (incluye qué se
consultó), sugerencias proactivas, advertencias de calidad de datos y costo visible por
respuesta.

### 📊 Insights automáticos (`/insights`)

Detección estadística pura (sin LLM en el cálculo): anomalías WoW ±10%, tendencias 3+
semanas, benchmarking de peers >1.5σ, oportunidades High Priority, correlaciones Spearman y
calidad de datos — priorizadas por **impacto ponderado por volumen de órdenes**
(`impact = severidad × (1 + ln(1 + órdenes))`). Dashboard con heatmap país×métrica, export
**Markdown/PDF** y **síntesis ejecutiva** redactada por Claude solo desde los números.

---

## Precisión: medida, no afirmada

```bash
cd backend
.venv/bin/python -m pytest tests/ -q          # 56 tests, sin costo de API
.venv/bin/python scripts/run_golden_live.py   # 9 casos por el agente real (~$0.19)
```

| Suite | Cubre |
|---|---|
| `test_golden_queries.py` (13) | Los 6 casos del brief congelados + aliases ES + self-healing + invariante de `valid_range` |
| `test_sql_guard.py` (26) | Matriz del guardia: SELECT/CTE/joins permitidos; UPDATE/DROP/multi-statement/`pg_sleep`/`pg_catalog`/otros schemas bloqueados; LIMIT inyectado/clampeado; integración real (rechazos auditados) |
| `test_api_auth.py` (14) | 401 sin token, JWT inválido/expirado, wiring de dependencias |
| `test_store.py` (3) | Ciclo completo de turno + **aislamiento entre usuarios** |
| Runner en vivo (9 casos) | Traducción NL→tool del agente real: herramienta esperada, parámetros, anclas, y **routing de tiers** (el nivel 2 solo se usa cuando hace falta) — última corrida 9/9 |

## Costos de API (Claude Sonnet 4.6)

| Operación | Costo medido |
|---|---|
| Primera pregunta de una sesión (escribe caché del system prompt) | ~$0.03 |
| Preguntas siguientes | ~$0.013–0.028 |
| **Sesión de 10 preguntas** | **~$0.15–0.25** |
| Síntesis ejecutiva de insights | ~$0.01 |
| Runner en vivo completo (9 preguntas) | ~$0.19 |

Tarifas: $3 input / $15 output / $0.30 cache-read / $3.75 cache-write por millón de tokens.

---

## Datos y reproducibilidad

`data/raw/dummydata.xlsx` → `prepare_data.py` (dedupe, tidy, **flags por `valid_range` del
catálogo**) → parquet verificados → `load_supabase.py` (COPY transaccional que **se revierte
si los counts o los spot-checks golden no cuadran**: 104.490 + 11.178 filas, 253 flags). El
motor carga un snapshot desde Supabase al arrancar, con fallback al parquet commiteado si la
red falla — la demo nunca muere.

## Estructura

```
├── enunciado.md
├── supabase/migrations/          # 0001 ops (datos + rol read-only) · 0002 app (chats + RLS)
├── backend/
│   ├── src/
│   │   ├── prepare_data.py       # ingesta + flags por catálogo
│   │   ├── metrics_catalog.json  # capa semántica (fuente de verdad)
│   │   ├── snapshot.py           # Supabase → DataFrames (fallback parquet)
│   │   ├── query_engine.py       # nivel 1: 8 herramientas deterministas
│   │   ├── sql_guard.py          # nivel 2: validación AST + rol RO + auditoría
│   │   ├── agent.py              # loop Claude + system prompt + tiers
│   │   ├── auth.py               # JWT de Supabase validado por JWKS (local)
│   │   ├── store.py              # conversaciones por usuario (api_history + replay)
│   │   ├── api.py                # REST: /chat SSE, /conversations, /insights
│   │   └── insights/             # detectores estadísticos + reporte
│   ├── scripts/                  # apply_migrations · load_supabase · seed_users · runner
│   └── tests/                    # 56 tests
├── frontend/src/
│   ├── app/                      # / landing · /login · /chat · /insights
│   ├── proxy.ts                  # gating de rutas (sesión en cookies)
│   └── components/               # chat (sidebar, replay, badges) · insights
└── docs/                         # ARCHITECTURE · Arquitectura-Nueva (plan v2) · PRESENTATION
```

## Decisiones, límites y siguientes pasos

Arquitectura y trade-offs (las 7 defensas contra el no-determinismo, por qué tool-use y no
text-to-SQL libre, por qué código y no n8n/Zapier, el diseño del nivel 2):
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · plan detallado de la v2:
[docs/Arquitectura-Nueva.md](docs/Arquitectura-Nueva.md).

**Limitaciones conocidas:**

- El nivel 2 garantiza que el SQL es seguro y los datos reales, pero no que la query
  interprete perfecto la intención — por eso el badge, el SQL visible y la auditoría.
- `api_history` crece con la conversación: truncado/resumen quedan anotados como mejora.
- Los hallazgos críticos de insights los domina Gross Profit UE (moneda vs ratios acotados):
  normalizar por volatilidad histórica es la siguiente iteración.
- Sin rate-limiting por usuario: fuera del alcance del caso.
