import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { delay, http, HttpResponse } from "msw";
import { App } from "../App";
import type { StoreSummary } from "../api/types";
import { STORAGE_KEYS } from "../config";
import { fixture, reply } from "../test/handlers";
import { server } from "../test/server";

const STORES = fixture("stores").body as StoreSummary[];
const name = (id: string) => STORES.find((s) => s.id === id)!.name;
const PANEER = "Marigold Farm Malai Paneer 200 g"; // not sold in Central, sold in Riverside
const NOWHERE = "zzqx wobble gadget"; // sold in neither
const BAGELS = "Daily Bake Plain Bagels 4 pack"; // sold in Central, not in Riverside

const wait = (ms: number) => act(() => new Promise((r) => setTimeout(r, ms)));
const box = () => screen.getByRole("combobox", { name: "Search products" });
const storeSelect = () => screen.getByRole("combobox", { name: "Store" });

/** Counts POST /search per store. */
function countSearches() {
  const calls: Record<string, number> = {};
  server.events.on("request:start", ({ request }) => {
    const m = request.url.match(/\/stores\/([^/]+)\/search$/);
    if (m) calls[m[1]!] = (calls[m[1]!] ?? 0) + 1;
  });
  return calls;
}

async function searchIn(store: string, text: string) {
  window.history.replaceState(null, "", `/?store=${store}`);
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("combobox", { name: "Store" });
  await user.type(box(), `${text}{Enter}`);
  const card = await screen.findByTestId("result-card");
  return { user, card };
}

it("says the product is not sold at this store, with what was asked for", async () => {
  const { card } = await searchIn("central", NOWHERE);
  expect(within(card).getByRole("heading")).toHaveTextContent(`“${NOWHERE}”`);
  expect(card).toHaveTextContent(`Not sold at ${name("central")}`);
  expect(within(card).getByRole("button", { name: `Check ${name("riverside")}` })).toBeInTheDocument();
});

it("hides the button when there is only one store", async () => {
  server.use(http.get("*/api/stores", () => HttpResponse.json(STORES.filter((s) => s.id === "central"))));
  const { card } = await searchIn("central", NOWHERE);
  expect(card).toHaveTextContent(`Not sold at ${name("central")}`);
  expect(within(card).queryByRole("button", { name: /^Check / })).not.toBeInTheDocument();
});

it("never checks the other store by itself", async () => {
  const calls = countSearches();
  await searchIn("central", NOWHERE);
  await wait(600);
  expect(calls).toEqual({ central: 1 });
  expect(storeSelect()).toHaveValue("central");
});

it("the button switches store (URL and storage) and runs the same search there once", async () => {
  const calls = countSearches();
  const { user, card } = await searchIn("central", PANEER);
  await user.click(within(card).getByRole("button", { name: `Check ${name("riverside")}` }));
  const found = await screen.findByRole("heading", { level: 3, name: PANEER });
  expect(found.closest("[data-testid=result-card]")).toHaveAttribute("data-status", "available");
  expect(storeSelect()).toHaveValue("riverside");
  expect(new URLSearchParams(window.location.search).get("store")).toBe("riverside");
  expect(localStorage.getItem(STORAGE_KEYS.store)).toBe("riverside");
  expect(box()).toHaveValue(PANEER);
  await wait(600);
  expect(calls).toEqual({ central: 1, riverside: 1 });
});

it("works the other way round too", async () => {
  const { user, card } = await searchIn("riverside", BAGELS);
  expect(card).toHaveTextContent(`Not sold at ${name("riverside")}`);
  await user.click(within(card).getByRole("button", { name: `Check ${name("central")}` }));
  const found = await screen.findByRole("heading", { level: 3, name: BAGELS });
  expect(found.closest("[data-testid=result-card]")).toHaveAttribute("data-status", "available");
});

it("if the other store lacks it too: 'Not found in either store', no button, no loop", async () => {
  const calls = countSearches();
  const { user, card } = await searchIn("central", NOWHERE);
  await user.click(within(card).getByRole("button", { name: `Check ${name("riverside")}` }));
  await screen.findByText("Not found in either store");
  expect(storeSelect()).toHaveValue("riverside");
  expect(screen.queryByRole("button", { name: /^Check / })).not.toBeInTheDocument();
  await wait(800);
  expect(calls).toEqual({ central: 1, riverside: 1 });
  expect(await axe(document.body)).toHaveNoViolations();
});

it("a new search after the check is an ordinary search again", async () => {
  const { user, card } = await searchIn("central", NOWHERE);
  await user.click(within(card).getByRole("button", { name: `Check ${name("riverside")}` }));
  await screen.findByText("Not found in either store");
  await user.clear(box());
  await user.type(box(), `${BAGELS}{Enter}`);
  const again = await screen.findByText(`Not sold at ${name("riverside")}`);
  expect(within(again.closest("[data-testid=result-card]")!).getByRole("button", { name: `Check ${name("central")}` })).toBeInTheDocument();
});

it("the other store's search is cancelled if the shopper switches back first", async () => {
  let aborted: boolean | null = null;
  server.use(
    http.post("*/api/stores/riverside/search", async ({ request }) => {
      await delay(500);
      aborted = request.signal.aborted;
      return reply("search_riverside_paneer");
    }),
  );
  const { user, card } = await searchIn("central", PANEER);
  await user.click(within(card).getByRole("button", { name: `Check ${name("riverside")}` }));
  await user.selectOptions(storeSelect(), "central");
  await wait(700);
  expect(aborted).toBe(true);
  expect(storeSelect()).toHaveValue("central");
  expect(screen.queryAllByTestId("result-card")).toHaveLength(0);
  expect(screen.getByText("What are you looking for?")).toBeInTheDocument();
});

it("a search with no items at all gets the same card", async () => {
  server.use(
    http.post("*/api/stores/central/search", () =>
      HttpResponse.json({ ...(fixture("search_central_not_found").body as object), items: [], status: "not_found" }),
    ),
  );
  window.history.replaceState(null, "", "/?store=central");
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("combobox", { name: "Store" });
  await user.type(box(), "nothing here{Enter}");
  expect(await screen.findByText(`Not sold at ${name("central")}`)).toBeInTheDocument();
  expect(screen.getByText("“nothing here”")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: `Check ${name("riverside")}` })).toBeInTheDocument();
});
