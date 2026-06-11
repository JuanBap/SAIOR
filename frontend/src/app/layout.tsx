import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Header } from "@/components/header";
import { ThemeProvider } from "@/components/theme-provider";

const geistSans = Geist({
  variable: "--font-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "SAIOR — Análisis Inteligente de Operaciones Rappi",
  description:
    "Bot conversacional de datos e insights automáticos sobre 980 zonas en 9 países de LATAM.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="es"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <ThemeProvider>
          <div
            aria-hidden
            className="pointer-events-none fixed inset-x-0 top-0 z-0 h-72 bg-[radial-gradient(55%_100%_at_50%_0%,rgba(255,68,31,0.07),transparent_70%)] print:hidden dark:bg-[radial-gradient(55%_100%_at_50%_0%,rgba(255,68,31,0.10),transparent_70%)]"
          />
          <Header />
          <main className="relative z-10 flex flex-1 flex-col">{children}</main>
        </ThemeProvider>
      </body>
    </html>
  );
}
