import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

// The one smoke test: home, store switch, search "milk", add to the list, "Find my route" with its map.
// Each project (360/1280 px, light/dark) saves screenshots to web/screenshots/smoke/.
const UPSTAIRS = "PlayTime Wax Crayons 12 pack"; // a Level 2 product in Central Store
const SHOTS = fileURLToPath(new URL("../screenshots/smoke/", import.meta.url));

async function noSidewaysScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

test("home, store switch, search, list and route with map", async ({ page }, info) => {
  const shot = (name: string) => page.screenshot({ path: `${SHOTS}${info.project.name}-${name}.png` });
  const theme = info.project.use.colorScheme as "light" | "dark";

  // Home loads, following the system theme.
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Find anything in Central Store" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Browse by category" }).getByRole("button").first()).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
  await noSidewaysScroll(page);
  await shot("01-home");

  // Store switch: the URL follows, and switching back works.
  const store = page.getByRole("combobox", { name: "Store" });
  await store.selectOption("riverside");
  await expect(page.getByRole("heading", { level: 1, name: "Find anything in Riverside Market" })).toBeVisible();
  await expect(page).toHaveURL(/store=riverside/);
  await store.selectOption("central");
  await expect(page.getByRole("heading", { level: 1, name: "Find anything in Central Store" })).toBeVisible();

  // Search "milk": the store asks which milk; choosing one shows its card and a collapsed route.
  const box = page.getByRole("combobox", { name: "Search products" });
  await box.fill("milk");
  await box.press("Enter");
  await expect(page.getByRole("heading", { name: "Which “milk” did you mean?" })).toBeVisible();
  await page.locator(".sf-option").first().click();
  const card = page.getByTestId("result-card").first();
  await expect(card).toHaveAttribute("data-status", "available");
  await expect(page.getByRole("region", { name: "Your route" })).toBeVisible();
  await noSidewaysScroll(page);
  await shot("02-results");

  // Add to the list (toast confirms). Add an upstairs product too, so the route changes floor.
  await card.getByRole("button", { name: /^Add .* to list$/ }).click();
  await expect(page.getByTestId("toast")).toContainText("to your list");
  await box.fill(UPSTAIRS);
  await box.press("Enter");
  await page.getByRole("button", { name: `Add ${UPSTAIRS} to list` }).click();
  await page.getByTestId("toast").getByRole("button", { name: "Open list" }).click();
  const sheet = page.getByRole("dialog", { name: "Shopping list" });
  await expect(sheet.getByRole("group", { name: /^Quantity of / })).toHaveCount(2);

  // Find my route: numbered steps, metres and floor changes, and a map of each floor it uses.
  await sheet.getByRole("button", { name: "Find my route" }).click();
  const route = sheet.getByRole("region", { name: "Your route" });
  await expect(route.getByRole("listitem").first()).toBeVisible();
  await expect(route).toContainText(/\d+ m/);
  await expect(route).toContainText("1 floor change");
  const maps = route.getByRole("img", { name: /^Map of Level \d+\./ });
  await expect(maps).toHaveCount(2);
  await expect(maps.first()).toHaveAttribute("aria-label", /then takes the .+ to Level 2\.$/);
  await noSidewaysScroll(page);
  await shot("03-list-route");
  // The maps can be taller than the sheet's scroll area; give the page room for the map-only picture.
  await page.setViewportSize({ width: page.viewportSize()!.width, height: 2000 });
  await maps.first().scrollIntoViewIfNeeded();
  await page.locator(".sf-map").first().screenshot({ path: `${SHOTS}${info.project.name}-04-map.png` });
});
