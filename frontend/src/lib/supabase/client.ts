"use client";

import { createBrowserClient } from "@supabase/ssr";

/** Cliente de Supabase para el navegador — SOLO se usa para auth (login, sesión,
 *  logout). Los datos y las conversaciones siempre pasan por la REST API. */
export const supabase = createBrowserClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
);
