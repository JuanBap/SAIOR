-- F3 · Schema app: conversaciones por usuario, mensajes para replay y auditoría SQL.

create schema if not exists app;

create table if not exists app.conversations (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  title       text not null default 'Nueva conversación',
  -- historial crudo del SDK de Anthropic (tool_use/tool_result) para CONTINUAR el chat:
  api_history jsonb not null default '[]',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists conversations_user_idx on app.conversations (user_id, updated_at desc);

create table if not exists app.messages (
  id              bigint generated always as identity primary key,
  conversation_id uuid not null references app.conversations(id) on delete cascade,
  role            text not null check (role in ('user', 'assistant')),
  -- payload renderizable por la UI tal cual se vio:
  --   user:      {"text": "..."}
  --   assistant: {"segments": [...], "tools": [...], "usage": {...}, "tier": "..."}
  content         jsonb not null,
  created_at      timestamptz not null default now()
);
create index if not exists messages_conversation_idx on app.messages (conversation_id, id);

-- Auditoría del nivel 2 (run_sql) — se llena a partir de F4.
create table if not exists app.query_log (
  id              bigint generated always as identity primary key,
  user_id         uuid references auth.users(id) on delete set null,
  conversation_id uuid references app.conversations(id) on delete set null,
  sql             text not null,
  ok              boolean not null,
  error           text,
  rows_returned   int,
  duration_ms     int,
  created_at      timestamptz not null default now()
);

-- ---------------------------------------------------------------- seguridad
-- El backend (rol postgres, dueño) scopea SIEMPRE por el user_id del JWT.
-- RLS queda activo como defensa en profundidad ante cualquier acceso directo.
alter table app.conversations enable row level security;
alter table app.messages enable row level security;
alter table app.query_log enable row level security;

drop policy if exists own_conversations on app.conversations;
create policy own_conversations on app.conversations
  for all to authenticated using (user_id = (select auth.uid()));

drop policy if exists own_messages on app.messages;
create policy own_messages on app.messages
  for all to authenticated using (
    exists (select 1 from app.conversations c
            where c.id = conversation_id and c.user_id = (select auth.uid()))
  );

drop policy if exists own_query_log on app.query_log;
create policy own_query_log on app.query_log
  for select to authenticated using (user_id = (select auth.uid()));

-- El rol del nivel 2 jamás toca app.* (sin grants = denegado; verificado en F0).
