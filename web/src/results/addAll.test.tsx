import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { App } from "../App";
import type { SearchResponse } from "../api/types";
import { LIST_MAX_ITEMS, STORAGE_KEYS } from "../config";
import type { ListItem } from "../list/list";
import { fixture } from "../test/handlers";

// "2 bagels, crayons, watercolours (out of stock) and a made-up product (not found)", recorded from the real API.
const MIXED = fixture("search_central_mixed");
const MIXED_TEXT = (MIXED.request.body as { text: string }).text;
const ITEMS = (MIXED.body as SearchResponse).items;
const IN_STOCK = ITEMS.filter((i) => i.status === "available");
const BAGELS = IN_STOCK.find((i) => i.quantity_requested > 1)!;

const stored = (): ListItem[] => JSON.parse(localStorage.getItem(STORAGE_KEYS.list("central")) ?? "[]");
const listed = (sku: string, name = `Product ${sku}`): ListItem => ({ sku, name, qty: 1, image_url: null, place: null });

async function searchMixed(preloaded: ListItem[] = []) {
  window.history.replaceState(null, "", "/?store=central");
  if (preloaded.length) localStorage.setItem(STORAGE_KEYS.list("central"), JSON.stringify(preloaded));
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("combobox", { name: "Store" });
  // Pasted: typing this long text key by key is slow and flaky in jsdom.
  await user.click(screen.getByRole("combobox", { name: "Search products" }));
  await user.paste(MIXED_TEXT);
  await user.keyboard("{Enter}");
  await screen.findAllByTestId("result-card");
  return user;
}
const addAll = () => screen.queryByRole("button", { name: "Add all to list" });
const toast = () => screen.getByTestId("toast");

it("the recorded search has 2 in stock, 1 out of stock and 1 not found, and asks for 2 bagels", () => {
  expect(ITEMS.map((i) => i.status)).toEqual(["available", "available", "unavailable", "not_found"]);
  expect(BAGELS.quantity_requested).toBe(2);
});

it("shows one Add all button above the cards when 2 or more items are in stock", async () => {
  await searchMixed();
  const button = addAll()!;
  expect(button).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "Add all to list" })).toHaveLength(1);
  const firstCard = screen.getAllByTestId("result-card")[0]!;
  expect(button.compareDocumentPosition(firstCard) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(await axe(screen.getByRole("region", { name: "Results" }))).toHaveNoViolations();
});

it("is not shown for a one-product search", async () => {
  window.history.replaceState(null, "", "/?store=central");
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("combobox", { name: "Store" });
  await user.type(screen.getByRole("combobox", { name: "Search products" }), "Daily Bake Plain Bagels 4 pack{Enter}");
  await screen.findByTestId("result-card");
  expect(addAll()).not.toBeInTheDocument();
});

it("adds the in-stock items with the asked quantity, skips the rest, and says so", async () => {
  const user = await searchMixed();
  await user.click(addAll()!);
  expect(stored().map((i) => [i.sku, i.qty])).toEqual(IN_STOCK.map((i) => [i.sku, i.quantity_requested]));
  expect(toast()).toHaveTextContent("Added 2 to your list. Skipped 2 that are out of stock or not found.");
  expect(screen.getByRole("button", { name: /^Shopping list/ })).toHaveAccessibleName("Shopping list, 2 items");
  // The cards now say they are in the list.
  for (const i of IN_STOCK) expect(screen.getByRole("button", { name: `${i.name} is in your list. Open list` })).toBeInTheDocument();
  // The toast opens the list; the quantity asked for is there.
  await user.click(within(toast()).getByRole("button", { name: "Open list" }));
  const sheet = screen.getByRole("dialog", { name: "Shopping list" });
  expect(within(within(sheet).getByRole("group", { name: `Quantity of ${BAGELS.name}` })).getByText("2")).toBeInTheDocument();
});

it("leaves items already in the list as they are and counts them", async () => {
  const user = await searchMixed([{ ...listed(BAGELS.sku!, BAGELS.name!), qty: 5 }]);
  await user.click(addAll()!);
  expect(stored().map((i) => [i.sku, i.qty])).toEqual([[BAGELS.sku, 5], [IN_STOCK[1]!.sku, 1]]);
  expect(toast()).toHaveTextContent("Added 1 to your list. 1 was already in it. Skipped 2 that are out of stock or not found.");
});

it(`stops at ${LIST_MAX_ITEMS} products with a friendly message`, async () => {
  const almost = Array.from({ length: LIST_MAX_ITEMS - 1 }, (_, k) => listed(`X-${k}`));
  const user = await searchMixed(almost);
  await user.click(addAll()!);
  expect(stored()).toHaveLength(LIST_MAX_ITEMS);
  expect(stored().at(-1)!.sku).toBe(IN_STOCK[0]!.sku);
  expect(toast()).toHaveTextContent(
    `Added 1 to your list. Your list is full (${LIST_MAX_ITEMS} products), so 1 didn't fit. Skipped 2 that are out of stock or not found.`,
  );
});

it("is disabled when the list is already full", async () => {
  await searchMixed(Array.from({ length: LIST_MAX_ITEMS }, (_, k) => listed(`X-${k}`)));
  expect(screen.getByRole("button", { name: "Add all to list" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Add all to list" })).toHaveAccessibleDescription(
    `Your list is full (${LIST_MAX_ITEMS} products).`,
  );
});
