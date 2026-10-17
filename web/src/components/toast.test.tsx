import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { App } from "../App";
import { LIST_MAX_ITEMS, STORAGE_KEYS, TOAST_MS } from "../config";

const CAP = "Basic Co Baseball Cap one size";

async function browseAndAdd() {
  window.history.replaceState(null, "", "/?store=central");
  const user = userEvent.setup();
  render(<App />);
  const nav = await screen.findByRole("navigation", { name: "Browse by category" });
  await user.click(within(nav).getByRole("button", { name: "Accessories, scarves & caps" }));
  const add = await screen.findByRole("button", { name: `Add ${CAP} to list` });
  await user.click(add);
  return user;
}
const toast = () => screen.queryByTestId("toast");

it("says what was added, in a polite live region, without taking focus", async () => {
  await browseAndAdd();
  expect(toast()).toHaveTextContent(`Added ${CAP} to your list`);
  expect(toast()!.closest("[aria-live]")).toHaveAttribute("aria-live", "polite");
  expect(screen.getByRole("button", { name: `${CAP} is in your list. Open list` })).toHaveFocus();
  expect(await axe(document.body)).toHaveNoViolations();
});

it("its action opens the list", async () => {
  const user = await browseAndAdd();
  await user.click(within(toast()!).getByRole("button", { name: "Open list" }));
  expect(screen.getByRole("dialog", { name: "Shopping list" })).toBeInTheDocument();
  expect(toast()).not.toBeInTheDocument();
});

it("can be closed", async () => {
  const user = await browseAndAdd();
  await user.click(within(toast()!).getByRole("button", { name: "Dismiss" }));
  expect(toast()).not.toBeInTheDocument();
});

it("goes away by itself", async () => {
  await browseAndAdd();
  await act(() => new Promise((r) => setTimeout(r, TOAST_MS + 200)));
  expect(toast()).not.toBeInTheDocument();
}, TOAST_MS + 10_000);

it("says when the list is now full", async () => {
  const items = Array.from({ length: LIST_MAX_ITEMS - 1 }, (_, i) => ({ sku: `X${i}`, name: `Thing ${i}`, qty: 1, image_url: null, place: null }));
  localStorage.setItem(STORAGE_KEYS.list("central"), JSON.stringify(items));
  await browseAndAdd();
  expect(toast()).toHaveTextContent(`Added ${CAP}. Your list is now full (${LIST_MAX_ITEMS} products).`);
});
