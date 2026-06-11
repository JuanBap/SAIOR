"""Métricas de observabilidad para la pestaña Lab — todo sale de lo ya persistido
en Supabase (app.messages.usage, app.query_log, app.conversations). Sin contadores
en memoria: si el backend se reinicia, las métricas no se pierden.
"""
from __future__ import annotations

import store

# Tarifas Claude Sonnet 4.6 (USD por token)
RATE_IN = 3e-6
RATE_OUT = 15e-6
RATE_CACHE_READ = 0.3e-6
RATE_CACHE_WRITE = 3.75e-6


def metrics() -> dict:
    with store._pool().connection() as conn:
        row = conn.execute("""
            select count(*),
                   coalesce(sum((content->'usage'->>'input_tokens')::bigint), 0),
                   coalesce(sum((content->'usage'->>'output_tokens')::bigint), 0),
                   coalesce(sum((content->'usage'->>'cache_read_input_tokens')::bigint), 0),
                   coalesce(sum((content->'usage'->>'cache_creation_input_tokens')::bigint), 0)
            from app.messages where role = 'assistant'
        """).fetchone()
        turns, tok_in, tok_out, tok_cr, tok_cw = (int(v) for v in row)  # sum() devuelve Decimal

        tiers = dict(conn.execute("""
            select coalesce(content->>'tier', 'verified'), count(*)
            from app.messages where role = 'assistant' group by 1
        """).fetchall())

        tools_freq = [
            {"name": r[0], "count": r[1]}
            for r in conn.execute("""
                select t->>'name', count(*)
                from app.messages, jsonb_array_elements(content->'tools') as t
                where role = 'assistant' group by 1 order by 2 desc
            """).fetchall()
        ]

        by_user = [
            {"email": r[0], "conversations": r[1], "turns": r[2]}
            for r in conn.execute("""
                select u.email, count(distinct c.id),
                       count(m.id) filter (where m.role = 'user')
                from auth.users u
                join app.conversations c on c.user_id = u.id
                left join app.messages m on m.conversation_id = c.id
                group by u.email order by 3 desc
            """).fetchall()
        ]

        q_total, q_ok, q_avg_ms = conn.execute("""
            select count(*), count(*) filter (where ok),
                   coalesce(avg(duration_ms) filter (where ok), 0)::int
            from app.query_log
        """).fetchone()

        recent_queries = [
            {
                "email": r[0], "ok": r[1], "sql": r[2], "error": r[3],
                "rows": r[4], "ms": r[5], "at": r[6].isoformat(),
            }
            for r in conn.execute("""
                select coalesce(u.email, 'script/test'), q.ok, q.sql, q.error,
                       q.rows_returned, q.duration_ms, q.created_at
                from app.query_log q left join auth.users u on u.id = q.user_id
                order by q.id desc limit 12
            """).fetchall()
        ]

        activity = [
            {"date": r[0].isoformat(), "turns": r[1]}
            for r in conn.execute("""
                select created_at::date, count(*)
                from app.messages where role = 'user'
                group by 1 order by 1 desc limit 14
            """).fetchall()
        ][::-1]

        n_convs = conn.execute("select count(*) from app.conversations").fetchone()[0]
        n_msgs = conn.execute("select count(*) from app.messages").fetchone()[0]

    cost = (tok_in * RATE_IN + tok_out * RATE_OUT
            + tok_cr * RATE_CACHE_READ + tok_cw * RATE_CACHE_WRITE)
    total_in = tok_in + tok_cr + tok_cw

    return {
        "usage": {
            "turns": turns,
            "input_tokens": tok_in,
            "output_tokens": tok_out,
            "cache_read_tokens": tok_cr,
            "cache_creation_tokens": tok_cw,
            "cache_hit_pct": round(tok_cr / total_in * 100, 1) if total_in else 0.0,
            "est_cost_usd": round(cost, 4),
            "avg_cost_per_turn_usd": round(cost / turns, 4) if turns else 0.0,
        },
        "tiers": {
            "verified": int(tiers.get("verified", 0)),
            "generated": int(tiers.get("generated", 0)),
        },
        "tools_freq": tools_freq,
        "conversations": {"total": n_convs, "messages": n_msgs, "by_user": by_user},
        "query_log": {
            "total": q_total, "ok": q_ok, "rejected": q_total - q_ok,
            "avg_ms": q_avg_ms, "recent": recent_queries,
        },
        "activity": activity,
    }
