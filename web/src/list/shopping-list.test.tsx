import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http } from "msw";
import { App } from "../App";
import type { SearchResponse } from "../api/types";
import { LIST_MAX_ITEMS, QTY_MAX, STORAGE_KEYS } from "../config";
import { fixture, reply } from "../test/handlers";
import { server } from "../test/server";
import type { ListItem } from "./list";

const BASKET = fixture("basket_central_route");
const ROUTE = (BASKET.body as SearchResponse).route!;
const basketItems = (BASKET.request.body as { items: { sku: string; qty: number }[] }).items;
const routeNames = (BASKET.body as SearchResponse).items.map((i) => i.name!);

const stored = (storeId: string): ListItem[] => JSON.parse(localStorage.getItem(STORAGE_KEYS.list(storeId)) ?? "[]");
function preload(storeId: string, items: ListItem[]) {
  localStorage.setItem(STORAGE_KEYS.list(storeId), JSON.stringify(items));
}
const listed = (sku: string, name: string, qty = 1): ListItem => ({ sku, name, qty, image_url: null, place: null });

async function home(store = "central") {
  window.history.replaceState(null, "", `/?store=${store}`);
  const user = userEvent.setup();
  const view = render(<App />);
  await screen.findByRole("combobox", { name: "Store" });
  return { user, view };
}
const listButton = () => screen.getByRole("button", { name: /^Shopping list/ });
async function openList(user: ReturnType<typeof userEvent.setup>) {
  await user.click(listButton());
  return screen.getByRole("dialog", { name: "Shopping list" });
}
async function browseAccessories(user: ReturnType<typeof userEvent.setup>) {
  const nav = await screen.findByRole("navigation", { name: "Browse by category" });
  await user.click(await within(nav).findByRole("button", { name: "Accessories, scarves & caps" }));
  await screen.findAllByTestId("result-card");
}

it("adds a product from a card; the card then says it is in the list", async () => {
  const { user } = await home();
  expect(listButton()).toHaveAccessibleName("Shopping list, empty");
  await browseAccessories(user);
  await user.click(screen.getByRole("button", { name: "Add Basic Co Baseball Cap one size to list" }));
  expect(listButton()).toHaveAccessibleName("Shopping list, 1 item");
  expect(screen.getByRole("button", { name: "Basic Co Baseball Cap one size is in your list. Open list" })).toBeInTheDocument();
  expect(stored("central")).toEqual([
    expect.objectContaining({ sku: "APP-ACC-003", name: "Basic Co Baseball Cap one size", qty: 1, place: expect.stringContaining("Level 2") }),
  ]);
});

it("keeps a separate list per store, and the list survives a reload", async () => {
  preload("central", [listed("APP-ACC-003", "Basic Co Baseball Cap one size", 3)]);
  const { user, view } = await home();
  expect(listButton()).toHaveAccessibleName("Shopping list, 1 item");
  await user.selectOptions(screen.getByRole("combobox", { name: "Store" }), "riverside");
  await waitFor(() => expect(listButton()).toHaveAccessibleName("Shopping list, empty"));
  view.unmount();
  await home("central");
  const sheet = await openList(userEvent.setup());
  expect(within(sheet).getByText("Basic Co Baseball Cap one size")).toBeInTheDocument();
  expect(within(sheet).getByRole("group", { name: "Quantity of Basic Co Baseball Cap one size" })).toHaveTextContent("3");
});

it("ignores a damaged stored list instead of crashing", async () => {
  localStorage.setItem(STORAGE_KEYS.list("central"), "{not json");
  await home();
  expect(listButton()).toHaveAccessibleName("Shopping list, empty");
});

it(`changes quantity with the stepper, between 1 and ${QTY_MAX}`, async () => {
  preload("central", [listed("A1", "Apples", 2), listed("B1", "Bread", QTY_MAX - 1)]);
  const { user } = await home();
  const sheet = await openList(user);
  const apples = within(sheet).getByRole("group", { name: "Quantity of Apples" });
  await user.click(within(apples).getByRole("button", { name: "One fewer Apples" }));
  expect(apples).toHaveTextContent("1");
  expect(within(apples).getByRole("button", { name: "One fewer Apples" })).toBeDisabled();
  const bread = within(sheet).getByRole("group", { name: "Quantity of Bread" });
  await user.click(within(bread).getByRole("button", { name: "One more Bread" }));
  expect(bread).toHaveTextContent(String(QTY_MAX));
  expect(within(bread).getByRole("button", { name: "One more Bread" })).toBeDisabled();
  expect(stored("central").map((i) => i.qty)).toEqual([1, QTY_MAX]);
  // The steppers are big enough to tap.
  for (const b of within(apples).getAllByRole("button")) expect(b).toHaveClass("sf-icon-button");
});

it("removes an item", async () => {
  preload("central", [listed("A1", "Apples"), listed("B1", "Bread")]);
  const { user } = await home();
  const sheet = await openList(user);
  await user.click(within(sheet).getByRole("button", { name: "Remove Apples" }));
  expect(within(sheet).queryByText("Apples")).not.toBeInTheDocument();
  expect(stored("central").map((i) => i.sku)).toEqual(["B1"]);
});

it("shows a friendly empty list", async () => {
  const { user } = await home();
  const sheet = await openList(user);
  expect(within(sheet).getByText("Your list is empty")).toBeInTheDocument();
  expect(within(sheet).queryByRole("button", { name: "Find my route" })).not.toBeInTheDocument();
});

it(`stops at ${LIST_MAX_ITEMS} products`, async () => {
  preload("central", Array.from({ length: LIST_MAX_ITEMS }, (_, i) => listed(`X${i}`, `Thing ${i}`)));
  const { user } = await home();
  await browseAccessories(user);
  const add = screen.getByRole("button", { name: "Add Basic Co Baseball Cap one size to list" });
  expect(add).toBeDisabled();
  expect(add).toHaveTextContent("List full");
});

describe("Find my route", () => {
  beforeEach(() => preload("central", basketItems.map((b, i) => listed(b.sku, routeNames[i]!, b.qty))));

  it("sends the list to POST /basket/route and shows numbered steps, metres and floor changes", async () => {
    const sent: unknown[] = [];
    server.events.on("request:start", async ({ request }) => {
      if (request.url.endsWith("/basket/route")) sent.push(await request.clone().json());
    });
    const { user } = await home();
    const sheet = await openList(user);
    await user.click(within(sheet).getByRole("button", { name: "Find my route" }));
    const route = await within(sheet).findByRole("region", { name: "Your route" });
    expect(sent).toEqual([{ items: basketItems }]);
    expect(within(route).getByText(`${Math.round(ROUTE.total_distance_m)} m`)).toBeInTheDocument();
    expect(route).toHaveTextContent(`${ROUTE.floor_changes} floor change`);
    const steps = within(route).getAllByRole("listitem");
    expect(steps.map((s) => s.textContent)).toEqual(ROUTE.steps.map((s) => expect.stringContaining(s.text)));
    expect(within(route).getByRole("button", { name: "Hide steps" })).toHaveAttribute("aria-expanded", "true");
    expect(await axe(sheet)).toHaveNoViolations();
  });

  it("clears the route when the list changes, so it is never out of date", async () => {
    const { user } = await home();
    const sheet = await openList(user);
    await user.click(within(sheet).getByRole("button", { name: "Find my route" }));
    await within(sheet).findByRole("region", { name: "Your route" });
    await user.click(within(sheet).getByRole("button", { name: `One more ${routeNames[1]}` }));
    expect(within(sheet).queryByRole("region", { name: "Your route" })).not.toBeInTheDocument();
  });

  it("clears the route when an item is removed", async () => {
    const { user } = await home();
    const sheet = await openList(user);
    await user.click(within(sheet).getByRole("button", { name: "Find my route" }));
    await within(sheet).findByRole("region", { name: "Your route" });
    await user.click(within(sheet).getByRole("button", { name: `Remove ${routeNames[0]}` }));
    expect(within(sheet).queryByRole("region", { name: "Your route" })).not.toBeInTheDocument();
  });

  it("clears the route when a product is added", async () => {
    const { user } = await home();
    let sheet = await openList(user);
    await user.click(within(sheet).getByRole("button", { name: "Find my route" }));
    await within(sheet).findByRole("region", { name: "Your route" });
    await user.keyboard("{Escape}");
    await browseAccessories(user);
    await user.click(screen.getByRole("button", { name: "Add Basic Co Baseball Cap one size to list" }));
    sheet = await openList(user);
    expect(within(sheet).queryByRole("region", { name: "Your route" })).not.toBeInTheDocument();
  });

  it("shows a friendly wait message when rate limited, with the reference", async () => {
    server.use(http.post("*/api/stores/central/basket/route", () => reply("error_rate_limited")));
    const { user } = await home();
    const sheet = await openList(user);
    await user.click(within(sheet).getByRole("button", { name: "Find my route" }));
    const alert = await within(sheet).findByRole("alert");
    expect(alert).toHaveTextContent("Lots of searches right now");
    expect(alert).toHaveTextContent("Reference: fixture-error_rate_limited");
  });
});

describe("collapsed route under a typed search", () => {
  it("starts collapsed and opens on tap", async () => {
    const { user } = await home();
    await user.type(screen.getByRole("combobox", { name: "Search products" }), "Daily Bake Plain Bagels 4 pack{Enter}");
    const route = await screen.findByRole("region", { name: "Your route" });
    const toggle = within(route).getByRole("button", { name: /^Show \d+ steps$/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(within(route).queryAllByRole("listitem")).toHaveLength(0);
    await user.click(toggle);
    expect(within(route).getAllByRole("listitem").length).toBeGreaterThan(0);
  });
});
