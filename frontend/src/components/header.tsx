"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { LayoutDashboard, MessageSquare } from "lucide-react";

import { getHealth } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Chat", icon: MessageSquare },
  { href: "/insights", label: "Insights", icon: LayoutDashboard },
] as const;

export function Header() {
  const pathname = usePathname();
  const [health, setHealth] = useState<"checking" | "ok" | "down">("checking");

  useEffect(() => {
    let alive = true;
    const check = async () => {
      const ok = await getHealth();
      if (alive) setHealth(ok ? "ok" : "down");
    };
    check();
    const id = setInterval(check, 20_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return (
    <header className="sticky top-0 z-20 border-b bg-background/80 backdrop-blur-md print:hidden">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-lg bg-rappi text-base font-black text-white shadow-[0_0_18px_rgba(255,68,31,0.45)]">
            R
          </span>
          <span className="leading-tight">
            <span className="block text-sm font-semibold tracking-tight">SAIOR</span>
            <span className="block text-[11px] text-muted-foreground">
              Análisis Inteligente · Operaciones Rappi
            </span>
          </span>
        </Link>

        <nav className="ml-auto flex items-center gap-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors",
                  active
                    ? "bg-rappi/15 font-medium text-rappi-soft"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </nav>

        <span
          className="flex items-center gap-1.5 text-[11px] text-muted-foreground"
          title={health === "ok" ? "Backend conectado" : "Backend no disponible (uvicorn api:app)"}
        >
          <span
            className={cn(
              "size-2 rounded-full",
              health === "ok" && "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]",
              health === "down" && "bg-red-500",
              health === "checking" && "animate-pulse bg-zinc-500",
            )}
          />
          API
        </span>
      </div>
    </header>
  );
}
