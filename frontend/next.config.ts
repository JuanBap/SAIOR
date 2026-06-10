import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    // Evita que Turbopack infiera otro root por lockfiles fuera del repo.
    root: path.join(__dirname),
  },
};

export default nextConfig;
