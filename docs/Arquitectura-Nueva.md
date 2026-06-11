# Arquitectura Nueva — SAIOR v2: Supabase + multiusuario + SQL de dos niveles

> Estado: **IMPLEMENTADO** (fases F0–F6 completas en `feat/supabase-architecture`).
> Verificación final: 56 tests backend + runner en vivo 9/9 (incluye caso nivel-2 y
> aserciones de routing por tier). Este documento queda como registro del plan y sus
> decisiones; la arquitectura as-built se resume en ARCHITECTURE.md y el README.

---

## 0. Objetivo

Evolucionar SAIOR de demo single-user a **producto multiusuario con persistencia**:

1. **Usuarios reales** (Supabase Auth): Juan, Mariana y Daniel tienen sus propias conversaciones.
2. **Persistencia de chats**: recargar la página no pierde nada; una conversación se puede
   continuar al día siguiente, eliminar, o empezar una nueva.
3. **Datos en Supabase**: `dummydata.xlsx` se carga a Postgres; la base deja de ser un parquet
   local y pasa a ser una base de datos real.
4. **Motor de consultas de dos niveles**: las queries verificadas de siempre + un nivel nuevo
   donde Claude **arma SQL** para preguntas que ningún tool cubre — con guardrails duros.
5. **Landing page** de un solo viewport que vende la solución.

### Decisiones ya tomadas (no reabrir sin causa)

| # | Decisión | Elección |
|---|---|---|
| D1 | Motor de tools verificados | **Híbrido**: snapshot de Supabase → pandas al arranque (tools intactos, golden tests 13/13); SQL dinámico va directo a Postgres |
| D2 | Autenticación | **Email + contraseña** con registro abierto + 3 usuarios demo pre-sembrados |
| D3 | SQL dinámico | **Guardrails completos + badge en UI** ("consulta verificada" vs "consulta generada") + log auditable |
| D4 | Ejecución | **Por fases**, un PR por fase contra `develop` |

### Principios que NO cambian

- **El LLM nunca inventa números**: en ambos niveles, todo número proviene del resultado de
  una consulta real (pandas o Postgres). La narración sigue anclada al JSON.
- Gráficos y tablas se construyen **en Python desde el resultado**, jamás por el LLM.
- `temperature = 0`, self-healing de errores, catálogo semántico como fuente de verdad.
- La golden suite (13 tests) debe seguir verde en TODAS las fases.

### Qué se relaja (con los ojos abiertos)

El nivel 2 introduce el riesgo de **query sintácticamente válida pero semánticamente
equivocada** (responde otra pregunta). Mitigaciones en §6. La UI lo declara con el badge:
transparencia sobre el nivel de garantía en lugar de fingir que no existe la diferencia.

---

## 1. Arquitectura objetivo

```
┌────────────────────────────────────────────────────────────────────┐
│ FRONTEND — Next.js                                                 │
│  /            landing pública (1 viewport, sin scroll)             │
│  /login       Supabase Auth (email+password)                       │
│  /chat        protegida · sidebar de conversaciones · replay       │
│  /insights    protegida                                            │
│  middleware: sin sesión → redirect /login                          │
└──────────────┬─────────────────────────────────────────────────────┘
               │  Authorization: Bearer <JWT de Supabase>
┌──────────────▼─────────────────────────────────────────────────────┐
│ BACKEND — FastAPI (REST API, dueño de TODA la lógica)              │
│  valida JWT (JWKS) → user_id                                       │
│  /chat (SSE) · /conversations CRUD · /insights · /health           │
│                                                                    │
│  AGENTE (Claude Sonnet 4.6, temp 0)                                │
│   ├── Nivel 1 · tools verificados (8) ──► pandas sobre SNAPSHOT    │
│   │     golden-tested · determinista      (cargado de Supabase)    │
│   └── Nivel 2 · run_sql ──► validador AST ──► Postgres (rol RO)    │
│         badge "generada" · LIMIT/timeout · query_log               │
└──────┬──────────────────────────────┬──────────────────────────────┘
       │ service_role (chats,         │ rol claude_readonly
       │ scoping por user_id del JWT) │ (solo SELECT sobre ops.*)
┌──────▼──────────────────────────────▼──────────────────────────────┐
│ SUPABASE (Postgres + Auth)                                         │
│  auth.users          ← Supabase Auth (email+password)              │
│  app.conversations   ← chats por usuario (RLS)                     │
│  app.messages        ← turnos con segments para replay (RLS)       │
│  app.query_log       ← auditoría de todo SQL del nivel 2           │
│  ops.metrics_long    ← 104.490 filas desde dummydata.xlsx          │
│  ops.orders_long     ← 11.178 filas                                │
└────────────────────────────────────────────────────────────────────┘
```

Separación de responsabilidades pedida: el frontend **nunca** habla con las tablas de datos
ni de chats directamente — todo pasa por la REST API. Supabase-js en el front se usa **solo**
para auth (login/registro/sesión). RLS queda activo igualmente como defensa en profundidad.

---

## 2. Modelo de datos en Supabase

Migrations versionadas en `supabase/migrations/*.sql` (commiteadas al repo).

### 2.1 Schema `ops` — los datos del caso

```sql
create schema if not exists ops;

create table ops.metrics_long (
  country             text not null,
  city                text not null,
  zone                text not null,
  zone_type           text not null,
  zone_prioritization text not null,
  metric              text not null,
  week                smallint not null check (week between -8 and 0),
  value               double precision,          -- null = sin dato esa semana
  quality_flag        text not null default 'OK',
  primary key (country, city, zone, metric, week)
);
create index on ops.metrics_long (metric, week);
create index on ops.metrics_long (country, zone_type);

create table ops.orders_long (
  country text not null,
  city    text not null,
  zone    text not null,
  week    smallint not null check (week between -8 and 0),
  value   double precision,
  primary key (country, city, zone, week)
);
create index on ops.orders_long (week);

-- catálogo consultable por el nivel 2 (espejo de metrics_catalog.json)
create table ops.metric_catalog (
  metric           text primary key,
  definition       text,
  format           text,
  higher_is_better boolean,
  valid_lo         double precision,
  valid_hi         double precision,
  caveat           text
);
```

### 2.2 Schema `app` — conversaciones y auditoría

```sql
create schema if not exists app;

create table app.conversations (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  title       text not null default 'Nueva conversación',
  -- historial crudo de Anthropic (tool_use/tool_result) para CONTINUAR la conversación:
  api_history jsonb not null default '[]',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index on app.conversations (user_id, updated_at desc);

create table app.messages (
  id              bigint generated always as identity primary key,
  conversation_id uuid not null references app.conversations(id) on delete cascade,
  role            text not null check (role in ('user','assistant')),
  -- payload para RE-RENDERIZAR la UI tal cual se vio:
  --   user:      {"text": "..."}
  --   assistant: {"segments":[{kind:text|chart|table,...}], "tools":[...],
  --               "usage":{...}, "tier":"verified|generated|mixed"}
  content         jsonb not null,
  created_at      timestamptz not null default now()
);
create index on app.messages (conversation_id, id);

create table app.query_log (
  id              bigint generated always as identity primary key,
  user_id         uuid references auth.users(id),
  conversation_id uuid references app.conversations(id) on delete set null,
  sql             text not null,
  ok              boolean not null,
  error           text,
  rows_returned   int,
  duration_ms     int,
  created_at      timestamptz not null default now()
);
```

**Dos representaciones del historial, a propósito:** `conversations.api_history` guarda los
mensajes crudos del SDK de Anthropic (necesarios para *continuar* la conversación con
contexto completo de tool calls); `app.messages.content` guarda los *segments* renderizables
(necesarios para que el replay reproduzca gráficos y tablas idénticos al recargar). Son
necesidades distintas; mezclarlas en una sola estructura complica ambas.

### 2.3 RLS y roles

```sql
alter table app.conversations enable row level security;
alter table app.messages      enable row level security;

create policy own_conversations on app.conversations
  for all using (user_id = auth.uid());
create policy own_messages on app.messages
  for all using (exists (select 1 from app.conversations c
                         where c.id = conversation_id and c.user_id = auth.uid()));

-- Rol del NIVEL 2: lo único que puede hacer es leer ops.*
create role claude_readonly nologin;
grant usage on schema ops to claude_readonly;
grant select on all tables in schema ops to claude_readonly;
alter role claude_readonly set statement_timeout = '5s';
-- sin grants sobre app.* ni auth.* → ni leyendo puede tocar chats/usuarios
```

El backend usa dos conexiones Postgres: la de servicio (ETL, snapshot, chats vía
service_role) y una **sesión con `set role claude_readonly`** exclusiva para el nivel 2.

---

## 3. ETL — carga del Excel a Supabase

`backend/scripts/load_supabase.py`:

1. Lee `data/processed/*.parquet` (ya validados por la golden suite; si se quiere desde el
   xlsx crudo, corre `prepare_data.py` antes).
2. Conecta por **Postgres directo** (pooler de Supabase, `SUPABASE_DB_URL`) y carga con
   `COPY` por lotes (104k filas ≈ segundos).
3. Idempotente: `truncate` + reload dentro de una transacción.
4. **Verificación al final**: counts exactos (104.490 / 11.178), flags = 253, y spot-checks
   de 3 valores golden (Perfect Orders MX Wealthy = 0.9043, etc.). Si algo no cuadra → rollback.
5. Carga también `ops.metric_catalog` desde `metrics_catalog.json`.

`backend/scripts/seed_users.py`: crea los usuarios demo vía Admin API (service_role) con
`email_confirm: true` — `juan@saior.demo`, `mariana@saior.demo`, `daniel@saior.demo` (password
en variable de entorno, no hardcodeada).

---

## 4. Autenticación de punta a punta

1. **Frontend**: `@supabase/supabase-js` + `@supabase/ssr`. Página `/login` propia (shadcn) con
   login y registro. La sesión vive en cookies; `middleware.ts` protege `/chat` y `/insights`.
2. **Cada request a la REST API** lleva `Authorization: Bearer <access_token>`.
3. **FastAPI** valida el JWT **localmente** (JWKS de
   `{SUPABASE_PROJECT_URL}/auth/v1/.well-known/jwks.json`, cacheado; PyJWT). Sin red por
   request. Dependencia `get_current_user()` → `user_id`; sin token válido → 401.
4. El backend **siempre** filtra conversaciones por el `user_id` del token (nunca confía en
   IDs del body). RLS es la segunda línea.
5. Expiración: supabase-js refresca el access token solo; si un SSE largo recibe 401 a mitad,
   el front reintenta con token fresco.

---

## 5. REST API — contratos

| Método y ruta | Auth | Descripción |
|---|---|---|
| `POST /chat` | ✅ | Body `{message, conversation_id?}`. Sin `conversation_id` crea conversación (título = primeras palabras; mejora futura: titulado por LLM). SSE igual que hoy + evento `meta` inicial con `{conversation_id}`. Al terminar persiste el turno (messages + api_history + usage) |
| `GET /conversations` | ✅ | Lista del usuario: `[{id, title, updated_at, preview}]` |
| `GET /conversations/{id}` | ✅ | Mensajes renderizables (`app.messages.content`) para el replay |
| `DELETE /conversations/{id}` | ✅ | Borra (cascade a messages) |
| `PATCH /conversations/{id}` | ✅ | Renombrar título |
| `GET /insights`, `/insights/markdown`, `/insights/narrative` | ✅ | Igual que hoy |
| `GET /health` | — | + estado de Supabase y modo del snapshot (db/fallback) |

`SESSIONS` (dict en memoria) **desaparece**: la memoria conversacional ahora es
`conversations.api_history` en Postgres. Continuar una conversación = cargar su
`api_history` y seguir — eso hace posible el caso "Daniel sigue al día siguiente".

---

## 6. Motor de dos niveles

### Nivel 1 — tools verificados (sin cambios funcionales)

- `query_engine.py` no cambia su API. Cambia **de dónde salen los DataFrames**: un
  `snapshot.py` nuevo que al arranque hace `SELECT * FROM ops.metrics_long / ops.orders_long`
  → DataFrames (mismos dtypes/columnas que el parquet).
- **Fallback de resiliencia**: si Supabase no responde al arranque, carga el parquet local y
  `/health` reporta `snapshot: "fallback-parquet"`. La demo nunca muere por la red.
- Criterio de aceptación permanente: **pytest 13/13 contra el snapshot de Supabase**.

### Nivel 2 — `run_sql` (lo nuevo)

Herramienta #9 del agente:

```
run_sql(sql: str, purpose: str)
  "Última opción: SOLO si ninguna otra herramienta puede responder. Escribe un único
   SELECT sobre ops.metrics_long / ops.orders_long / ops.metric_catalog.
   purpose = qué pregunta de negocio responde (queda auditado)."
```

**Pipeline de ejecución** (todo en `backend/src/sql_guard.py`, testeado unitariamente):

1. **Parseo AST** con `sqlglot` (dialecto postgres). Falla el parseo → error al modelo.
2. **Reglas** (todas o se rechaza):
   - exactamente 1 statement; tipo `SELECT` (CTEs `WITH ... SELECT` permitidos);
   - tablas referenciadas ⊆ {`ops.metrics_long`, `ops.orders_long`, `ops.metric_catalog`};
   - prohibido: `pg_catalog`, `information_schema`, funciones de sistema (`pg_sleep`,
     `set_config`, `current_setting`...), subconsultas a otros schemas, `INTO`;
   - `LIMIT` ≤ 500 (se inyecta `LIMIT 500` si falta).
3. **Ejecución** en la conexión `claude_readonly` (statement_timeout 5s). El rol no tiene
   grants fuera de `ops` → aunque una regla fallara, Postgres es el muro final.
4. **Resultado** → JSON {columns, rows, rowcount} al modelo + evento `table` a la UI con
   `tier: "generated"` + el SQL visible (expandible) para el usuario curioso.
5. **Auditoría**: insert en `app.query_log` (sql, ok, error, filas, duración, user, conv).
6. **Self-healing**: error de Postgres → mensaje estructurado → el modelo corrige (máx 2).

**Contexto que recibe el modelo** (system prompt, sección nueva): DDL compacto de las 3
tablas, semántica de WEEK, 3 ejemplos de SQL bien formado, y la regla de oro de routing:
*"si un tool tipado puede responder, ÚSALO; run_sql es el último recurso y debes decir en
purpose por qué ningún tool servía"*.

**Badge en UI**: cada respuesta lleva `tier`: `verified` (solo tools 1), `generated` (usó
run_sql) o `mixed`. Chip visible: ✅ "consulta verificada" / 🧪 "consulta generada (SQL
auditado)". Es transparencia, y en la demo es un argumento — no un parche.

**Feature flag**: `RUN_SQL_ENABLED=true|false` — permite demo sin nivel 2 si hiciera falta.

---

## 7. Frontend

### 7.1 Landing `/` (pública, 1 viewport sin scroll)

Layout en grid de 2 columnas sobre el tema oscuro Rappi existente:

- **Izquierda**: logo SAIOR + h1 ("Pregúntale a tus operaciones. Respuestas que no
  alucinan.") + subtítulo de una línea + 4 bullets ganadores:
  1. ✅ El LLM nunca calcula — cada número sale de una consulta real y auditada
  2. 📊 Insights automáticos priorizados por impacto de negocio (volumen de órdenes)
  3. 🔁 Dos niveles de consulta: verificadas con tests + SQL generado con guardrails
  4. 🧪 Precisión medida: 13 tests golden + suite en vivo 8/8
  + CTA: botón "Entrar" → `/login` (y "Ver la arquitectura" → ancla al diagrama del README/PR).
- **Derecha**: mini-diagrama de la arquitectura (SVG estático: Frontend → REST API →
  motor 2 niveles → Supabase) con los mismos colores del producto.
- Header mínimo (logo + Entrar). Sin footer. Verificar sin scroll a 1366×768 y 1440×900.

### 7.2 App

- `/chat`: **sidebar** de conversaciones (lista ordenada por `updated_at`, botón "Nueva",
  hover → eliminar con confirmación, click → carga y **replay** desde `messages.content` —
  los gráficos/tablas se re-renderizan idénticos porque son JSON determinista).
- Header: email del usuario + logout.
- Badge de tier por respuesta (§6).
- `/insights`: igual + protegida.
- Estado de sesión: `@supabase/ssr` con cookies; `middleware.ts` para gating.

---

## 8. Testing

| Suite | Qué cubre | Cuándo |
|---|---|---|
| `tests/test_golden_queries.py` (existente, intocable) | Nivel 1 sobre snapshot | Cada fase |
| `tests/test_sql_guard.py` (nuevo) | El validador AST: matriz de casos permitidos (SELECT, CTE, agregaciones) y bloqueados (UPDATE/DELETE/DROP, multi-statement, `pg_sleep`, `pg_catalog`, tablas `app.*`, sin LIMIT → inyectado) | F4 |
| `tests/test_api_auth.py` (nuevo) | 401 sin token, 200 con JWT válido (firmado con clave de test), scoping por user_id, CRUD de conversaciones | F2–F3 |
| `scripts/run_golden_live.py` (extendido) | + 2 preguntas que fuerzan nivel 2 (verificar badge `generated` y SQL en query_log) + verificación del router (las 6 del brief deben seguir resolviendo por nivel 1) | F4+ |
| `scripts/load_supabase.py` (auto-verificación) | Counts y spot-checks golden post-carga | F0 |

---

## 9. Fases de implementación (un PR por fase, contra `develop`)

> Prerrequisito: mergear PR #1 (`feat/project-starter → develop`) para que esta rama
> muestre solo su delta.

| Fase | Contenido | Criterio de aceptación (verificable) |
|---|---|---|
| **F0 — Datos en Supabase** | Migrations `ops.*` + rol `claude_readonly` + `load_supabase.py` + `seed_users.py` + deps (`psycopg`, `sqlglot`, `PyJWT`) | Counts exactos + spot-checks golden en Postgres; usuarios demo logueables en el dashboard de Supabase |
| **F1 — Snapshot del motor** | `snapshot.py` (Supabase → DataFrames, fallback parquet) cableado a `query_engine` | `pytest` 13/13 con datos venidos de Supabase; `/health` reporta la fuente |
| **F2 — Auth** | `/login` + middleware + validación JWT en FastAPI + `get_current_user` en todos los endpoints | Sin token → 401; test E2E de login con usuario demo; `test_api_auth.py` verde |
| **F3 — Persistencia de chats** | Migrations `app.*` + RLS + endpoints conversations + persistencia por turno + sidebar + replay | Recargar conserva todo; continuar conversación de ayer funciona; eliminar borra en cascade; Juan no ve los chats de Mariana (test) |
| **F4 — Nivel 2 (run_sql)** | `sql_guard.py` + tool + conexión readonly + badge + `query_log` + flag | `test_sql_guard.py` verde; pregunta no cubierta (ej. "mediana de Perfect Orders por ciudad en CO") responde con badge `generated` y queda en query_log; las 6 del brief siguen por nivel 1 |
| **F5 — Landing** | `/` pública de 1 viewport; rutas protegidas movidas | Sin scroll en 1366×768/1440×900; CTA → login → chat |
| **F6 — Docs y cierre** | README, ARCHITECTURE, PRESENTATION actualizados; runner extendido; `.env.example`s completos | Runner en vivo todo verde (8 originales + nivel 2); docs sin referencias a la arquitectura vieja |

Estimación honesta: F0–F1 ≈ ½ día · F2 ≈ ½ día · F3 ≈ 1 día · F4 ≈ 1 día · F5 ≈ ½ día ·
F6 ≈ ½ día. **Total ≈ 4 días** de trabajo efectivo.

---

## 10. Variables de entorno

**backend/.env** (las SUPABASE_* ya existen):

```
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-sonnet-4-6
FRONTEND_ORIGIN=http://localhost:3000
SUPABASE_PROJECT_URL=https://<proyecto>.supabase.co
SUPABASE_PUBLIC_KEY=<anon/publishable>
SUPABASE_SERVICE_ROLE_KEY=<service-role>          # solo backend, JAMÁS al front
SUPABASE_DATABASE_PASSWORD=<password>             # para armar SUPABASE_DB_URL
SUPABASE_DB_URL=postgresql://...pooler.supabase.com:5432/postgres   # derivable
DEMO_USERS_PASSWORD=<para seed_users.py>
RUN_SQL_ENABLED=true
```

**frontend/.env.local** (nuevo):

```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://<proyecto>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon/publishable>   # la PUBLIC_KEY; es segura en el cliente
```

---

## 11. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Supabase caído durante la demo | Snapshot con fallback a parquet local (bot e insights siguen); chats degradan con aviso visible, no con crash |
| SQL malicioso/curioso vía prompt injection ("borra las tablas") | 3 muros: routing del prompt → validador AST → rol Postgres sin permisos de escritura ni acceso a `app`/`auth`. El peor caso real: un SELECT raro con LIMIT 500 y timeout 5s |
| Query generada que malinterpreta la intención | Badge `generated` + SQL visible/expandible + query_log auditable + el prompt exige declarar `purpose`. Riesgo residual aceptado y comunicado |
| Latencia de arranque (snapshot) | Carga directa por Postgres (~2–4s) y cache parquet; lazy si hiciera falta |
| `api_history` crece sin límite | Aceptable en demo; anotado: truncado a últimos N turnos / resumen como mejora futura |
| Token expira a mitad de un SSE largo | Refresh client-side + reintento del request |
| Free tier de Supabase | Datos ≈ 15–20 MB en Postgres + chats: holgadísimo dentro de 500 MB |
| Regresión del nivel 1 durante la migración | La golden suite corre en cada fase; F1 no se mergea sin 13/13 contra Supabase |

---

## 12. Qué NO cambia

- Las 8 herramientas y sus números (golden suite intacta).
- El insights engine completo (consume el mismo snapshot).
- El protocolo SSE de eventos (`token/tool/chart/table/done/error`) — solo se agregan
  `meta.conversation_id` y `tier`.
- El principio de narración anclada y los visuales deterministas.
- Tema visual, componentes del chat, página /insights.
