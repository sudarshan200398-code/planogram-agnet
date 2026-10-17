import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { App } from "../App";
import type { Category } from "../api/types";
import { QUICK_CATEGORY_COUNT } from "../config";
import { fixture } from "../test/handlers";
import { quickCategories } from "./useCategories";

const central = (fixture("categories_central").body as { categories: Category[] }).categories;
const browsed = fixture("products_central_page").request.query.category as string;

async function home() {
  window.history.replaceState(null, "", "/");
  const user = userEvent.setup();
  render(<App />);
  const nav = await screen.findByRole("navigation", { name: "Browse by category" });
  return { user, nav };
}

it("picks the largest categories for the quick chips, ties alphabetical", () => {
  const quick = quickCategories(central, QUICK_CATEGORY_COUNT);
  expect(quick).toHaveLength(QUICK_CATEGORY_COUNT);
  for (let i = 1; i < quick.length; i++) {
    const [a, b] = [quick[i - 1]!, quick[i]!];
    expect(a.product_count > b.product_count || (a.product_count === b.product_count && a.name < b.name)).toBe(true);
  }
});

it("shows quick chips plus 'More categories' for the store", async () => {
  const { nav } = await home();
  const chips = within(nav).getAllByRole("button");
  expect(chips).toHaveLength(QUICK_CATEGORY_COUNT + 1);
  expect(chips.at(-1)).toHaveTextContent("More categories");
  expect(within(nav).getByRole("button", { name: browsed })).toHaveAttribute("aria-pressed", "false");
});

it("browses a category page by page, and tapping the chip again clears it", async () => {
  const { user, nav } = await home();
  await user.click(within(nav).getByRole("button", { name: browsed }));
  expect(await screen.findByRole("heading", { name: `${browsed} (8)` })).toBeInTheDocument();
  expect(screen.getAllByTestId("result-card")).toHaveLength(4);
  await user.click(screen.getByRole("button", { name: "Show more (4 left)" }));
  expect(await screen.findAllByTestId("result-card")).toHaveLength(8);
  expect(screen.queryByRole("button", { name: /Show more/ })).not.toBeInTheDocument();
  await user.click(within(nav).getByRole("button", { name: browsed }));
  expect(screen.queryAllByTestId("result-card")).toHaveLength(0);
  expect(screen.getByText("What are you looking for?")).toBeInTheDocument();
});

it("lists every category in a sheet that closes with Escape and returns focus", async () => {
  const { user, nav } = await home();
  const more = within(nav).getByRole("button", { name: "More categories" });
  await user.click(more);
  const dialog = screen.getByRole("dialog", { name: "All categories" });
  expect(within(dialog).getAllByRole("listitem")).toHaveLength(central.length);
  expect(await axe(dialog)).toHaveNoViolations();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(more).toHaveFocus();
});

it("picking from the sheet browses that category", async () => {
  const { user, nav } = await home();
  await user.click(within(nav).getByRole("button", { name: "More categories" }));
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: new RegExp(`^${browsed.replace(/[()]/g, "\\$&")}`) }));
  expect(await screen.findByRole("heading", { name: `${browsed} (8)` })).toBeInTheDocument();
});

it("loads the other store's categories after switching store", async () => {
  const { user } = await home();
  await user.selectOptions(screen.getByRole("combobox", { name: "Store" }), "riverside");
  const riverside = (fixture("categories_riverside").body as { categories: Category[] }).categories;
  const expected = quickCategories(riverside, QUICK_CATEGORY_COUNT)[0]!.name;
  expect(await screen.findByRole("button", { name: expected })).toBeInTheDocument();
});

it("a search replaces the category view", async () => {
  const { user, nav } = await home();
  await user.click(within(nav).getByRole("button", { name: browsed }));
  await screen.findByRole("heading", { name: `${browsed} (8)` });
  await user.type(screen.getByRole("combobox", { name: "Search products" }), "Daily Bake Plain Bagels 4 pack{Enter}");
  expect(await screen.findByRole("heading", { name: /Results for/ })).toBeInTheDocument();
  expect(within(nav).getByRole("button", { name: browsed })).toHaveAttribute("aria-pressed", "false");
});
