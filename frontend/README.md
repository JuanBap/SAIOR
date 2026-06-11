# SAIOR — Frontend

UI del bot conversacional y del dashboard de insights. Next.js 16 (App Router) +
Tailwind v4 + shadcn/ui + Recharts.

```bash
pnpm install
pnpm dev        # http://localhost:3000 (espera el backend en :8000)
```

Configuración opcional en `.env` (ver `.env.example`): `NEXT_PUBLIC_API_URL` si el
backend no corre en `http://localhost:8000`.

Setup completo, arquitectura y decisiones: **[README raíz](../README.md)** y
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
