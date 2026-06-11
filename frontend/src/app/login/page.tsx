"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, Loader2, LogIn, UserPlus } from "lucide-react";

import { supabase } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const fn =
      mode === "signin"
        ? supabase.auth.signInWithPassword({ email, password })
        : supabase.auth.signUp({ email, password });
    const { error } = await fn;
    setLoading(false);
    if (error) {
      setError(
        error.message === "Invalid login credentials"
          ? "Credenciales inválidas. Revisa email y contraseña."
          : error.message,
      );
      return;
    }
    router.replace(params.get("next") ?? "/chat");
    router.refresh();
  }

  return (
    <div className="grid flex-1 place-items-center px-4 py-10">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="mb-2 flex items-center gap-2.5">
            <span className="grid size-9 place-items-center rounded-lg bg-rappi text-base font-black text-white shadow-[0_0_18px_rgba(255,68,31,0.45)]">
              R
            </span>
            <span className="text-lg font-semibold tracking-tight">SAIOR</span>
          </div>
          <CardTitle className="text-xl">
            {mode === "signin" ? "Inicia sesión" : "Crea tu cuenta"}
          </CardTitle>
          <CardDescription>
            {mode === "signin"
              ? "Tus conversaciones con los datos te esperan."
              : "Registro con email y contraseña (mínimo 6 caracteres)."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-3">
            <Input
              type="email"
              required
              placeholder="email@empresa.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoFocus
            />
            <Input
              type="password"
              required
              minLength={6}
              placeholder="contraseña"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {error && (
              <p className="flex items-start gap-1.5 text-xs text-red-600 dark:text-red-300">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                {error}
              </p>
            )}
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? (
                <Loader2 data-icon="inline-start" className="animate-spin" />
              ) : mode === "signin" ? (
                <LogIn data-icon="inline-start" />
              ) : (
                <UserPlus data-icon="inline-start" />
              )}
              {mode === "signin" ? "Entrar" : "Registrarme"}
            </Button>
          </form>

          <button
            onClick={() => {
              setMode(mode === "signin" ? "signup" : "signin");
              setError(null);
            }}
            className="mt-3 w-full text-center text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            {mode === "signin" ? "¿No tienes cuenta? Regístrate" : "¿Ya tienes cuenta? Inicia sesión"}
          </button>

          <div className="mt-4 rounded-lg border border-rappi/25 bg-rappi/8 p-3 text-[11px] leading-relaxed text-muted-foreground">
            <p className="mb-1 font-medium text-rappi-soft">Usuarios demo</p>
            juan@saior.demo · mariana@saior.demo · daniel@saior.demo
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
