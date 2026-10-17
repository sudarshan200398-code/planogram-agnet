import { defineConfig } from "@playwright/test";

/**
 * One smoke test (e2e/smoke.spec.ts) against the real API with the AI model off, in Chromium,
 * at phone and desktop width, in light and dark. Run: npm run e2e (servers already running are reused).
 */
const API_PORT = 8000;
const WEB_PORT = 5173;

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  workers: 1, // the API keeps sessions in one process; run the projects one after another
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    browserName: "chromium",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "360-light", use: { viewport: { width: 360, height: 780 }, colorScheme: "light", deviceScaleFactor: 2 } },
    { name: "360-dark", use: { viewport: { width: 360, height: 780 }, colorScheme: "dark", deviceScaleFactor: 2 } },
    { name: "1280-light", use: { viewport: { width: 1280, height: 800 }, colorScheme: "light" } },
    { name: "1280-dark", use: { viewport: { width: 1280, height: 800 }, colorScheme: "dark" } },
  ],
  webServer: [
    {
      command: `python -m uvicorn api.main:app --host 127.0.0.1 --port ${API_PORT} --workers 1`,
      cwd: "..",
      url: `http://127.0.0.1:${API_PORT}/health`,
      env: { PLANOGRAM_PROVIDER: "none" },
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: `npm run dev -- --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
