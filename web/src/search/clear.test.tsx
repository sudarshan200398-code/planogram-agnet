import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http } from "msw";
import { App } from "../App";
import type { SearchResponse } from "../api/types";
import { STORAGE_KEYS, SUGGEST_DEBOUNCE_MS } from "../config";
import type { ListItem } from "../list/list";
import { fixture, reply } from "../test/handlers";
import { server } from "../test/server";

const MILK = fixture("search_central_milk").body as SearchResponse;
const BAGELS = "Daily Bake Plain Bagels 4 pack";
const BASKET = fixture("basket_central_route");
const basketItems = (BASKET.request.body as { items: { sku: string; qty: number }[] }).items;

const wait = (ms: number) => act(() => new Promise((r) => setTimeout(r, ms)));
const box = () => screen.getByRole("combobox", { name: "Search products" });
const home = () => screen.queryByText("What are you looking for?");
/** True when the suggestion list is showing any options. */
const suggestionsShown = () => {
  const list = document.querySelector<HTMLElement>('[role="listbox"][aria-label="Suggestions"]');
  return !!list && !list.hidden && list.querySelectorAll('[role="option"]').length > 0;
};

async function start() {
  window.history.replaceState(null, "", "/?store=central");
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("combobox", { name: "Store" });
  return user;
}

async function searchBagels(user: ReturnType<typeof userEvent.setup>) {
  await user.type(box(), `${BAGELS}{Enter}`);
  await screen.findByRole("region", { name: "Your route" });
}

function expectHome() {
  expect(home()).toBeInTheDocument();
  expect(screen.queryAllByTestId("result-card")).toHaveLength(0);
  expect(screen.queryByRole("region", { name: "Your route" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /Results for/ })).not.toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "Browse by category" })).toBeInTheDocument();
}

describe("emptying the search box returns to home", () => {
  it("backspacing to empty drops the results and their route", async () => {
    const user = await start();
    await searchBagels(user);
    await user.click(box());
    await user.keyboard("{Backspace}".repeat(BAGELS.length));
    expect(box()).toHaveValue("");
    expectHome();
  });

  it("the clear button drops the results and their route", async () => {
    const user = await start();
    await searchBagels(user);
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(box()).toHaveValue("");
    expectHome();
    expect(box()).toHaveFocus();
  });

  it("Escape closes suggestions first, then a second Escape empties the box and goes home", async () => {
    server.use(http.get("*/api/stores/central/suggest", () => reply("suggest_central_mi"))); // always some suggestions
    const user = await start();
    await searchBagels(user);
    await user.click(box());
    await user.type(box(), " x");
    await waitFor(() => expect(suggestionsShown()).toBe(true));
    await user.keyboard("{Escape}");
    expect(suggestionsShown()).toBe(false);
    expect(box()).toHaveValue(`${BAGELS} x`);
    await user.keyboard("{Escape}");
    expect(box()).toHaveValue("");
    expectHome();
  });

  it("a search still on its way when the box is emptied is cancelled and never shown", async () => {
    let aborted: boolean | null = null;
    server.use(
      http.post("*/api/stores/central/search", async ({ request }) => {
        await delay(400);
        aborted = request.signal.aborted;
        return reply("search_central_bagels");
      }),
    );
    const user = await start();
    await user.type(box(), `${BAGELS}{Enter}`);
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    await wait(600);
    expect(aborted).toBe(true);
    expectHome();
  });

  it("a suggestion request on its way when the box is emptied is cancelled and never shown", async () => {
    let aborted: boolean | null = null;
    server.use(
      http.get("*/api/stores/central/suggest", async ({ request }) => {
        await delay(400);
        aborted = request.signal.aborted;
        return reply("suggest_central_mi");
      }),
    );
    const user = await start();
    await user.type(box(), "mi");
    await wait(SUGGEST_DEBOUNCE_MS + 50); // the request has started
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    await wait(600);
    expect(aborted).toBe(true);
    expect(suggestionsShown()).toBe(false);
  });

  it("keeps the shopping list and its route", async () => {
    const names = (BASKET.body as SearchResponse).items.map((i) => i.name!);
    const list: ListItem[] = basketItems.map((b, i) => ({ sku: b.sku, name: names[i]!, qty: b.qty, image_url: null, place: null }));
    localStorage.setItem(STORAGE_KEYS.list("central"), JSON.stringify(list));
    const user = await start();
    await user.click(screen.getByRole("button", { name: /^Shopping list/ }));
    await user.click(screen.getByRole("button", { name: "Find my route" }));
    await within(screen.getByRole("dialog")).findByRole("region", { name: "Your route" });
    await user.keyboard("{Escape}");
    await searchBagels(user);
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expectHome();
    await user.click(screen.getByRole("button", { name: /^Shopping list, 2 items/ }));
    const sheet = screen.getByRole("dialog", { name: "Shopping list" });
    expect(within(sheet).getByRole("region", { name: "Your route" })).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(STORAGE_KEYS.list("central"))!)).toEqual(list);
  });
});

describe("switching store", () => {
  it("clears results, suggestions and a pending question", async () => {
    const user = await start();
    await user.type(box(), "milk{Enter}");
    await screen.findByRole("heading", { name: /did you mean/ });
    await user.type(box(), "{Backspace}{Backspace}"); // "mi": suggestions open
    await waitFor(() => expect(suggestionsShown()).toBe(true));
    await user.selectOptions(screen.getByRole("combobox", { name: "Store" }), "riverside");
    expect(box()).toHaveValue("");
    expect(screen.queryByRole("heading", { name: /did you mean/ })).not.toBeInTheDocument();
    expectHome();
    await wait(SUGGEST_DEBOUNCE_MS + 100);
    expect(suggestionsShown()).toBe(false);
  });

  it("an answer still on its way from the old store is ignored", async () => {
    server.use(
      http.post("*/api/stores/central/clarify", async () => {
        await delay(400);
        return reply("clarify_central_milk");
      }),
    );
    const user = await start();
    await user.type(box(), "milk{Enter}");
    await screen.findByRole("heading", { name: /did you mean/ });
    await user.click(screen.getByRole("button", { name: new RegExp(`^${MILK.question!.options[0]!.name}`) }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Store" }), "riverside");
    await wait(600);
    expectHome();
  });

  it("never shows the old store's list route", async () => {
    const names = (BASKET.body as SearchResponse).items.map((i) => i.name!);
    localStorage.setItem(
      STORAGE_KEYS.list("central"),
      JSON.stringify(basketItems.map((b, i) => ({ sku: b.sku, name: names[i]!, qty: b.qty, image_url: null, place: null }))),
    );
    const user = await start();
    await user.click(screen.getByRole("button", { name: /^Shopping list/ }));
    await user.click(screen.getByRole("button", { name: "Find my route" }));
    await within(screen.getByRole("dialog")).findByRole("region", { name: "Your route" });
    await user.keyboard("{Escape}");
    await user.selectOptions(screen.getByRole("combobox", { name: "Store" }), "riverside");
    await user.selectOptions(screen.getByRole("combobox", { name: "Store" }), "central");
    await user.click(screen.getByRole("button", { name: /^Shopping list/ }));
    await waitFor(() => expect(within(screen.getByRole("dialog")).queryByRole("region", { name: "Your route" })).not.toBeInTheDocument());
  });
});
