// Progress screenshots at phone width (360px) in light and dark, using Playwright's Chromium.
// Needs the API (PLANOGRAM_PROVIDER=none) on 127.0.0.1:8000 and the web app on localhost:5173.
// Usage: node scripts/progress-shots.mjs <step>   (writes web/screenshots/progress/<step>-<scene>-360-<theme>.png)
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const BASE = process.env.WEB_URL ?? "http://localhost:5173";
const step = process.argv[2] ?? "step";
const outDir = new URL("../screenshots/progress/", import.meta.url);
mkdirSync(outDir, { recursive: true });

const SCENES = {
  step1: {
    "search-suggestions": async (page) => {
      await page.goto(`${BASE}/?store=central`);
      await page.getByRole("combobox", { name: "Search products" }).fill("mi");
      await page.getByRole("listbox", { name: "Suggestions" }).getByRole("option").first().waitFor();
    },
    "category-browse": async (page) => {
      await page.goto(`${BASE}/?store=central`);
      const nav = page.getByRole("navigation", { name: "Browse by category" });
      await nav.getByRole("button").first().click();
      await page.getByTestId("result-card").first().waitFor();
      await page.waitForLoadState("networkidle");
    },
  },
  step4: {
    "list-and-route": async (page) => {
      await page.goto(`${BASE}/?store=central`);
      await page.getByRole("combobox", { name: "Search products" }).fill("Daily Bake Plain Bagels 4 pack and Store Brand Shredded Cheddar 400 g");
      await page.keyboard.press("Enter");
      for (const add of await page.getByRole("button", { name: /^Add .* to list$/ }).all()) await add.click();
      await page.getByRole("button", { name: /^Shopping list/ }).click();
      await page.getByRole("button", { name: "Find my route" }).click();
      await page.getByRole("heading", { name: "Your route" }).waitFor();
      await page.waitForLoadState("networkidle");
    },
  },
};

const scenes = SCENES[step];
if (!scenes) throw new Error(`unknown step ${step}`);
const browser = await chromium.launch();
const written = [];
for (const theme of ["light", "dark"]) {
  const context = await browser.newContext({ viewport: { width: 360, height: 780 }, colorScheme: theme, deviceScaleFactor: 2 });
  for (const [name, run] of Object.entries(scenes)) {
    const page = await context.newPage();
    await run(page);
    await page.evaluate(() => document.fonts?.ready);
    const file = fileURLToPath(new URL(`${step}-${name}-360-${theme}.png`, outDir));
    await page.screenshot({ path: file, fullPage: false });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    written.push(`${file}  (horizontal overflow: ${overflow})`);
    await page.close();
  }
  await context.close();
}
await browser.close();
console.log(written.join("\n"));
