/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { defineConfig, loadEnv } from "vite";
import { resolveApiBase } from "./src/lib/apiBase";

/** The security headers Vercel sends (vercel.json), so `vite preview` serves the same ones for local checks. */
function vercelHeaders(): Record<string, string> {
  const config = JSON.parse(readFileSync(new URL("./vercel.json", import.meta.url), "utf-8")) as {
    headers: { source: string; headers: { key: string; value: string }[] }[];
  };
  const all = config.headers.find((h) => h.source === "/(.*)")?.headers ?? [];
  return Object.fromEntries(all.map((h) => [h.key, h.value]));
}

// In development the API runs on 127.0.0.1:8000 and is proxied under /api, so no CORS is needed locally.
// In production set VITE_API_BASE_URL to the API's URL (and PLANOGRAM_CORS_ORIGINS on the API).
export default defineConfig(({ command, mode }) => {
  // A production build must know where the API is; stop here rather than ship an app that calls the wrong host.
  if (command === "build" && mode === "production") {
    const { error } = resolveApiBase(loadEnv(mode, process.cwd(), "VITE_").VITE_API_BASE_URL, true);
    if (error) throw new Error(error);
  }
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
    preview: { headers: vercelHeaders() },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.test.{ts,tsx}"],
      css: false,
      restoreMocks: true,
      // The fixtures are found with import.meta.glob; the persistent module cache does not notice new
      // fixture files and would serve the old list, so it stays off.
      fsModuleCache: false,
    },
  };
});
