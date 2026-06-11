-- F0 · Schema ops: los datos del caso (cargados desde dummydata.xlsx por load_supabase.py)
-- y el rol de solo-lectura que usará el nivel 2 (run_sql) del agente.

create schema if not exists ops;

create table if not exists ops.metrics_long (
  country             text not null,
  city                text not null,
  zone                text not null,
  zone_type           text not null,
  zone_prioritization text not null,
  metric              text not null,
  week                smallint not null check (week between -8 and 0),
  value               double precision,           -- null = sin dato esa semana
  quality_flag        text not null default 'OK',
  primary key (country, city, zone, metric, week)
);
create index if not exists metrics_long_metric_week_idx on ops.metrics_long (metric, week);
create index if not exists metrics_long_country_type_idx on ops.metrics_long (country, zone_type);

create table if not exists ops.orders_long (
  country text not null,
  city    text not null,
  zone    text not null,
  week    smallint not null check (week between -8 and 0),
  value   double precision,
  primary key (country, city, zone, week)
);
create index if not exists orders_long_week_idx on ops.orders_long (week);

-- Espejo consultable del catálogo semántico (metrics_catalog.json es la fuente de verdad;
-- esta tabla existe para que el nivel 2 pueda hacer JOIN/consultar definiciones por SQL).
create table if not exists ops.metric_catalog (
  metric           text primary key,
  definition       text,
  format           text,
  higher_is_better boolean,
  valid_lo         double precision,
  valid_hi         double precision,
  caveat           text
);

-- ---------------------------------------------------------------- seguridad
-- ops no se expone por la API REST de Supabase (PostgREST solo expone 'public');
-- igualmente revocamos a los roles de la API por defensa en profundidad.
revoke all on schema ops from anon, authenticated;
revoke all on all tables in schema ops from anon, authenticated;

-- Rol del nivel 2: SOLO puede leer ops.*. Sin login propio: el backend hace SET ROLE.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'claude_readonly') then
    create role claude_readonly nologin;
  end if;
end$$;

grant usage on schema ops to claude_readonly;
grant select on all tables in schema ops to claude_readonly;
alter default privileges in schema ops grant select on tables to claude_readonly;
-- defensa en profundidad (el ejecutor además hace SET LOCAL statement_timeout por query):
alter role claude_readonly set statement_timeout = '5s';
-- permite que la conexión del backend (usuario postgres) baje privilegios con SET ROLE:
grant claude_readonly to postgres;
