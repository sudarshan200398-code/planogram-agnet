import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";
import { App } from "../App";
import type { SearchResponse, StoreMap } from "../api/types";
import { STORAGE_KEYS } from "../config";
import { fixture, reply } from "../test/handlers";
import { server } from "../test/server";
import type { ListItem } from "./list";

// "I'm at the bakery, …": the search response's route starts at the Bakery; the list route then starts there too.
const SENTENCE = fixture("search_central_bakery_start");
const SENTENCE_TEXT = (SENTENCE.request.body as { text: string }).text;
const DETECTED = (SENTENCE.body as SearchResponse).route!;
const FROM_START = fixture("basket_central_two_from_bakery");
const FROM_ENTRANCE = fixture("basket_central_two");
const START_LABEL = (FROM_START.request.body as { start: string }).start;
const MAP = fixture("map_central").body as StoreMap;
const ENTRANCE = MAP.nodes.find((n) => n.type === "entrance")!.label;
const TWO = (FROM_ENTRANCE.request.body as { items: { sku: string; qty: number }[] }).items;
const twoItems = (): ListItem[] =>
  (FROM_ENTRANCE.body as SearchResponse).items.map((i, k) => ({ sku: i.sku!, name: i.name!, qty: TWO[k]!.qty, image_url: null, place: null }));

/** Bodies sent to POST /basket/route, in order. */
function basketBodies() {
  const sent: unknown[] = [];
  server.events.on("request:start", async ({ request }) => {
    if (request.url.endsWith("/basket/route")) sent.push(await request.clone().json());
  });
  return sent;
}

async function home(store = "central") {
  window.history.replaceState(null, "", `/?store=${store}`);
  localStorage.setItem(STORAGE_KEYS.list("central"), JSON.stringify(twoItems()));
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("combobox", { name: "Store" });
  return user;
}
async function searchSentence(user: ReturnType<typeof userEvent.setup>) {
  // Pasted: typing this long text key by key is slow and flaky in jsdom.
  await user.click(screen.getByRole("combobox", { name: "Search products" }));
  await user.paste(SENTENCE_TEXT);
  await user.keyboard("{Enter}");
  await screen.findAllByTestId("result-card");
}
async function openList(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /^Shopping list/ }));
  return screen.getByRole("dialog", { name: "Shopping list" });
}
const startLine = (sheet: HTMLElement) => within(sheet).queryByText(/^Starting from:/);

it("the recorded sentence really starts somewhere other than the entrance", () => {
  expect(DETECTED.start_label).toBe(START_LABEL);
  expect(DETECTED.start_label).not.toBe(ENTRANCE);
});

it("a start found in a search is shown in the list and used for Find my route", async () => {
  const sent = basketBodies();
  const user = await home();
  await searchSentence(user);
  const sheet = await openList(user);
  await waitFor(() => expect(startLine(sheet)).toHaveTextContent(`Starting from: ${START_LABEL}`));
  expect(await axe(sheet)).toHaveNoViolations();
  await user.click(within(sheet).getByRole("button", { name: "Find my route" }));
  const route = await within(sheet).findByRole("region", { name: "Your route" });
  expect(sent).toEqual([FROM_START.request.body]);
  expect(route).toHaveTextContent(`From ${START_LABEL}`);
});

it(`"Reset to ${ENTRANCE}" drops the start, clears its route, and the next route starts at the entrance`, async () => {
  const sent = basketBodies();
  const user = await home();
  await searchSentence(user);
  const sheet = await openList(user);
  await waitFor(() => expect(startLine(sheet)).not.toBeNull());
  await user.click(within(sheet).getByRole("button", { name: "Find my route" }));
  await within(sheet).findByRole("region", { name: "Your route" });

  await user.click(within(sheet).getByRole("button", { name: `Reset to ${ENTRANCE}` }));
  expect(startLine(sheet)).toBeNull();
  expect(within(sheet).queryByRole("region", { name: "Your route" })).not.toBeInTheDocument();
  await user.click(within(sheet).getByRole("button", { name: "Find my route" }));
  const route = await within(sheet).findByRole("region", { name: "Your route" });
  expect(sent).toEqual([FROM_START.request.body, FROM_ENTRANCE.request.body]);
  expect(route).toHaveTextContent(`From ${ENTRANCE}`);
});

it("shows no start line when the search route starts at the entrance", async () => {
  const sent = basketBodies();
  const user = await home();
  await user.type(screen.getByRole("combobox", { name: "Search products" }), "Daily Bake Plain Bagels 4 pack{Enter}");
  await screen.findByTestId("result-card");
  const sheet = await openList(user);
  expect(startLine(sheet)).toBeNull();
  expect(within(sheet).queryByRole("button", { name: /^Reset to / })).not.toBeInTheDocument();
  await user.click(within(sheet).getByRole("button", { name: "Find my route" }));
  await within(sheet).findByRole("region", { name: "Your route" });
  expect(sent).toEqual([FROM_ENTRANCE.request.body]);
});

it("clears the start when the store changes, even after switching back", async () => {
  const sent = basketBodies();
  const user = await home();
  await searchSentence(user);
  let sheet = await openList(user);
  await waitFor(() => expect(startLine(sheet)).not.toBeNull());
  await user.keyboard("{Escape}");

  const store = screen.getByRole("combobox", { name: "Store" });
  await user.selectOptions(store, "riverside");
  await screen.findByRole("heading", { level: 1, name: /Riverside/ });
  await user.selectOptions(store, "central");
  await screen.findByRole("heading", { level: 1, name: /Central/ });

  sheet = await openList(user);
  expect(startLine(sheet)).toBeNull();
  await user.click(within(sheet).getByRole("button", { name: "Find my route" }));
  await within(sheet).findByRole("region", { name: "Your route" });
  expect(sent).toEqual([FROM_ENTRANCE.request.body]);
});

it("does not keep a start the store's map does not know", async () => {
  const unknown = { ...MAP, nodes: MAP.nodes.filter((n) => n.id !== DETECTED.start_node) };
  server.use(http.get("*/api/stores/central/map", () => HttpResponse.json(unknown)));
  const user = await home();
  await searchSentence(user);
  const sheet = await openList(user);
  // Give the map request time to answer, then check nothing was kept.
  await waitFor(() => expect(within(sheet).getByRole("button", { name: "Find my route" })).toBeEnabled());
  await new Promise((r) => setTimeout(r, 100));
  expect(startLine(sheet)).toBeNull();
});

it("explains kindly when the API rejects the start point", async () => {
  const bad = fixture("basket_central_two_bad_start");
  expect((bad.body as SearchResponse).route).toBeNull(); // what the real API does: 200, partial, no route
  server.use(http.post("*/api/stores/central/basket/route", () => reply("basket_central_two_bad_start")));
  const user = await home();
  await searchSentence(user);
  const sheet = await openList(user);
  await waitFor(() => expect(startLine(sheet)).not.toBeNull());
  await user.click(within(sheet).getByRole("button", { name: "Find my route" }));
  expect(
    await within(sheet).findByText(`We couldn't start your route from ${START_LABEL}. Tap “Reset to ${ENTRANCE}” and try again.`),
  ).toBeInTheDocument();
  expect(within(sheet).queryByText(/Unknown start point/)).not.toBeInTheDocument();
  expect(within(sheet).queryByText("We couldn't make a route for this list.")).not.toBeInTheDocument();
});
