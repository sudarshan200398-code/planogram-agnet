import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { delay, http, HttpResponse } from "msw";
import { useState } from "react";
import { SUGGEST_DEBOUNCE_MS } from "../config";
import { fixture, reply } from "../test/handlers";
import { server } from "../test/server";
import { SearchBar } from "./SearchBar";

const miNames = (fixture("suggest_central_mi").body as { suggestions: { name: string }[] }).suggestions.map((s) => s.name);

function Harness({ onSearch = () => {}, storeId = "central" }: { onSearch?: (t: string) => void; storeId?: string }) {
  const [text, setText] = useState("");
  return <SearchBar storeId={storeId} text={text} onTextChange={setText} onSearch={onSearch} />;
}

function countSuggestRequests() {
  const seen: string[] = [];
  server.events.on("request:start", ({ request }) => {
    if (request.url.includes("/suggest")) seen.push(new URL(request.url).searchParams.get("q") ?? "");
  });
  return seen;
}

const box = () => screen.getByRole("combobox", { name: "Search products" });

it("shows suggestions with place and stock after the debounce", async () => {
  const user = userEvent.setup();
  render(<Harness />);
  await user.type(box(), "mi");
  const options = await screen.findAllByRole("option");
  expect(options.map((o) => within(o).getByText(/./, { selector: ".sf-suggest__name" }).textContent)).toEqual(miNames);
  expect(options[0]).toHaveTextContent(/Level \d, .+ · (In stock|Out of stock|Stock unknown)/);
  expect(box()).toHaveAttribute("aria-expanded", "true");
});

it("waits for typing to stop: one request for 'mi', none for one letter", async () => {
  const seen = countSuggestRequests();
  const user = userEvent.setup();
  render(<Harness />);
  await user.type(box(), "m");
  await new Promise((r) => setTimeout(r, SUGGEST_DEBOUNCE_MS + 100));
  expect(seen).toEqual([]);
  await user.type(box(), "i");
  await screen.findAllByRole("option");
  expect(seen).toEqual(["mi"]);
});

it("cancels a stale request so a slow old answer never replaces the newer one", async () => {
  const user = userEvent.setup();
  server.use(
    http.get("*/api/stores/central/suggest", async ({ request }) => {
      const q = new URL(request.url).searchParams.get("q");
      if (q === "mi") {
        await delay(600);
        return reply("suggest_central_mi");
      }
      const real = (fixture("suggest_central_mi").body as { suggestions: Record<string, unknown>[] }).suggestions[3];
      return HttpResponse.json({ store_id: "central", suggestions: [{ ...real, name: "Newer answer" }] });
    }),
  );
  render(<Harness />);
  await user.type(box(), "mi");
  await new Promise((r) => setTimeout(r, SUGGEST_DEBOUNCE_MS + 50)); // the slow "mi" request is now in flight
  await user.type(box(), "l");
  expect(await screen.findByText("Newer answer")).toBeInTheDocument();
  await new Promise((r) => setTimeout(r, 700));
  expect(screen.getAllByRole("option")).toHaveLength(1);
  expect(screen.queryByText(miNames[0]!)).not.toBeInTheDocument();
});

it("picks a suggestion with the keyboard and searches that exact product", async () => {
  const onSearch = vi.fn();
  const user = userEvent.setup();
  render(<Harness onSearch={onSearch} />);
  await user.type(box(), "mi");
  await screen.findAllByRole("option");
  await user.keyboard("{ArrowDown}{ArrowDown}");
  expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");
  expect(box()).toHaveAttribute("aria-activedescendant", screen.getAllByRole("option")[1]!.id);
  await user.keyboard("{Enter}");
  expect(onSearch).toHaveBeenCalledWith(miNames[1]);
  expect(box()).toHaveValue(miNames[1]);
  expect(screen.queryByRole("option")).not.toBeInTheDocument();
});

it("picks a suggestion by tapping it", async () => {
  const onSearch = vi.fn();
  const user = userEvent.setup();
  render(<Harness onSearch={onSearch} />);
  await user.type(box(), "mi");
  await user.click((await screen.findAllByRole("option"))[2]!);
  expect(onSearch).toHaveBeenCalledWith(miNames[2]);
});

it("submits the whole sentence when no suggestion is highlighted", async () => {
  const onSearch = vi.fn();
  const user = userEvent.setup();
  render(<Harness onSearch={onSearch} />);
  await user.type(box(), "milk, bread and crayons, I'm at produce{Enter}");
  expect(onSearch).toHaveBeenCalledWith("milk, bread and crayons, I'm at produce");
});

it("Escape closes the list and the clear button empties the bar", async () => {
  const user = userEvent.setup();
  render(<Harness />);
  await user.type(box(), "mi");
  await screen.findAllByRole("option");
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("option")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Clear search" }));
  expect(box()).toHaveValue("");
});

it("shows no suggestions (and no error) if suggest fails", async () => {
  server.use(http.get("*/api/stores/central/suggest", () => reply("error_rate_limited")));
  const user = userEvent.setup();
  render(<Harness />);
  await user.type(box(), "mi");
  await act(() => new Promise((r) => setTimeout(r, SUGGEST_DEBOUNCE_MS + 100)));
  await waitFor(() => expect(screen.queryByRole("option")).not.toBeInTheDocument());
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("has no accessibility violations with suggestions open", async () => {
  const user = userEvent.setup();
  const { container } = render(<Harness />);
  await user.type(box(), "mi");
  await screen.findAllByRole("option");
  expect(await axe(container)).toHaveNoViolations();
});
