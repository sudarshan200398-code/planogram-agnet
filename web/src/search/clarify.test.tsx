import { act, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { delay, http, HttpResponse } from "msw";
import { App } from "../App";
import type { SearchResponse } from "../api/types";
import { fixture, reply } from "../test/handlers";
import { server } from "../test/server";
import { useSearch } from "./useSearch";

const MILK = fixture("search_central_milk").body as SearchResponse;
const SENTENCE = "milk, bread and crayons, I'm at produce";

/** Counts API calls by kind, so tests can prove there are no extra or repeated requests. */
function countCalls() {
  const calls = { search: 0, clarify: 0 };
  server.events.on("request:start", ({ request }) => {
    if (request.url.endsWith("/search")) calls.search++;
    if (request.url.endsWith("/clarify")) calls.clarify++;
  });
  return calls;
}

async function startSearch(text: string) {
  window.history.replaceState(null, "", "/?store=central");
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("combobox", { name: "Store" });
  await user.type(screen.getByRole("combobox", { name: "Search products" }), `${text}{Enter}`);
  return user;
}

const question = () => screen.findByRole("heading", { name: /^Which “.+” did you mean\?$/ });
const option = (name: string) => screen.getByRole("button", { name: new RegExp(`^${name}`) });
const SLOW_TEST_MS = 15_000; // these tests deliberately wait for late responses
const wait = (ms: number) => act(() => new Promise((r) => setTimeout(r, ms)));

describe("the answer stays", () => {
  it("after later renders: no new requests and the question does not come back", async () => {
    const calls = countCalls();
    const user = await startSearch("milk");
    expect(await question()).toHaveTextContent("Which “milk” did you mean?");
    const chosen = MILK.question!.options[0]!;
    await user.click(option(chosen.name));

    const card = await screen.findByTestId("result-card");
    expect(within(card).getByRole("heading")).toHaveTextContent(chosen.name);
    expect(screen.queryByRole("heading", { name: /did you mean/ })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Your route" })).toBeInTheDocument();
    const before = { ...calls };

    // Many later renders: typing, theme changes, opening and closing a sheet, time passing.
    await user.type(screen.getByRole("combobox", { name: "Search products" }), " and more");
    await user.click(screen.getByRole("button", { name: /^Theme:/ }));
    await user.click(screen.getByRole("button", { name: /^Theme:/ }));
    await user.click(screen.getByRole("button", { name: "More categories" }));
    await user.keyboard("{Escape}");
    await wait(400);

    expect(calls).toEqual(before);
    expect(within(screen.getByTestId("result-card")).getByRole("heading")).toHaveTextContent(chosen.name);
    expect(screen.queryByRole("heading", { name: /did you mean/ })).not.toBeInTheDocument();
  });
});

describe("several items needing a choice", () => {
  it("asks them one after another, each answer sent to the right item, ending with a route", async () => {
    const asked: string[] = [];
    const sent: unknown[] = [];
    server.events.on("request:start", async ({ request }) => {
      if (request.url.endsWith("/clarify")) sent.push(await request.clone().json());
    });
    const user = await startSearch(SENTENCE);
    for (const step of [1, 2, 3]) {
      const q = await question();
      asked.push(q.textContent ?? "");
      const expectedBody = fixture(`clarify_central_sentence_${step}`).request.body as { sku: string };
      const name = (step === 1 ? fixture("search_central_sentence") : fixture(`clarify_central_sentence_${step - 1}`)).body as SearchResponse;
      const pick = name.question!.options.find((o) => o.sku === expectedBody.sku)!;
      await user.click(option(pick.name));
      await waitFor(() => expect(sent).toHaveLength(step));
    }
    expect(asked).toEqual(["Which “milk” did you mean?", "Which “bread” did you mean?", "Which “crayons” did you mean?"]);
    expect(sent.map((b) => (b as { item_index: number }).item_index)).toEqual([0, 1, 2]);
    expect(await screen.findByRole("heading", { name: "Your route" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /did you mean/ })).not.toBeInTheDocument();
    expect(screen.getAllByTestId("result-card").map((c) => c.dataset.status)).toEqual(["available", "available", "available"]);
  });
});

describe("409 SESSION_NOT_FOUND on /clarify", () => {
  it("re-runs the search once and re-sends the same choice once, then succeeds", async () => {
    const calls = countCalls();
    let first = true;
    server.use(
      http.post("*/api/stores/central/clarify", async ({ request }) => {
        if (first) {
          first = false;
          return reply("error_session_not_found");
        }
        const body = (await request.json()) as { sku: string };
        expect(body.sku).toBe(MILK.question!.options[1]!.sku);
        return reply("clarify_central_milk");
      }),
    );
    const user = await startSearch("milk");
    await question();
    await user.click(option(MILK.question!.options[1]!.name));
    expect(await screen.findByTestId("result-card")).toBeInTheDocument();
    expect(calls).toEqual({ search: 2, clarify: 2 });
  });

  it("never loops: if the retry also gets 409 it stops with a friendly error", async () => {
    const calls = countCalls();
    server.use(http.post("*/api/stores/central/clarify", () => reply("error_session_not_found")));
    const user = await startSearch("milk");
    await question();
    await user.click(option(MILK.question!.options[0]!.name));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("That question has expired");
    expect(alert).toHaveTextContent("Reference: fixture-error_session_not_found");
    await wait(800);
    expect(calls).toEqual({ search: 2, clarify: 2 });
  });

  it("if the choice is no longer offered after the re-run, shows the new question and asks again", async () => {
    let searches = 0;
    server.use(
      http.post("*/api/stores/central/clarify", () => reply("error_session_not_found")),
      http.post("*/api/stores/central/search", () => {
        searches++;
        if (searches === 1) return reply("search_central_milk");
        const body = structuredClone(MILK); // the re-run no longer offers the first option
        body.question!.options = body.question!.options.slice(1);
        return HttpResponse.json(body);
      }),
    );
    const calls = countCalls();
    const user = await startSearch("milk");
    await question();
    await user.click(option(MILK.question!.options[0]!.name));
    expect(await screen.findByRole("status")).toHaveTextContent("Please choose again");
    expect(screen.queryByRole("button", { name: new RegExp(`^${MILK.question!.options[0]!.name}`) })).not.toBeInTheDocument();
    expect(calls).toEqual({ search: 2, clarify: 1 });
  });
});

describe("a choice cannot be overwritten by a stale response", () => {
  it("a second tap while the first answer is on its way is ignored", async () => {
    const calls = countCalls();
    server.use(
      http.post("*/api/stores/central/clarify", async () => {
        await delay(300);
        return reply("clarify_central_milk");
      }),
    );
    const user = await startSearch("milk");
    await question();
    await user.click(option(MILK.question!.options[0]!.name));
    expect(option(MILK.question!.options[1]!.name)).toBeDisabled();
    await user.click(option(MILK.question!.options[1]!.name));
    await screen.findByTestId("result-card");
    expect(calls.clarify).toBe(1);
  });

  it("a slow answer that arrives after a newer search does not replace the newer results", async () => {
    server.use(
      http.post("*/api/stores/central/clarify", async () => {
        await delay(2500); // still on its way after the newer search has finished
        return reply("clarify_central_milk");
      }),
    );
    const user = await startSearch("milk");
    await question();
    await user.click(option(MILK.question!.options[0]!.name));
    const box = screen.getByRole("combobox", { name: "Search products" });
    await user.clear(box);
    await user.type(box, "Daily Bake Plain Bagels 4 pack{Enter}");
    expect(await screen.findByRole("heading", { name: "Results for “Daily Bake Plain Bagels 4 pack”" })).toBeInTheDocument();
    await wait(2700);
    const cards = screen.getAllByTestId("result-card");
    expect(cards).toHaveLength(1);
    expect(within(cards[0]!).getByRole("heading")).toHaveTextContent("Daily Bake Plain Bagels 4 pack");
  }, SLOW_TEST_MS);

  it("a late response from an earlier search does not replace the answered question", async () => {
    let n = 0;
    server.use(
      http.post("*/api/stores/central/search", async () => {
        n++;
        if (n === 1) {
          await delay(1500); // the first search is slow, superseded, and would show different results
          return reply("search_central_bagels");
        }
        return reply("search_central_milk");
      }),
    );
    // In the app a second search can start while one is loading (e.g. picking a suggestion); drive the hook directly.
    const { result } = renderHook(() => useSearch("central"));
    let slow: Promise<void> = Promise.resolve();
    act(() => {
      slow = result.current.search("bagels"); // starts, then is superseded
    });
    await act(async () => {
      await result.current.search("milk");
    });
    expect(result.current.state).toMatchObject({ status: "done", text: "milk" });
    await act(async () => {
      await result.current.answer(MILK.question!.item_index, MILK.question!.options[0]!.sku);
    });
    expect(result.current.state).toMatchObject({ status: "done", response: { status: "ok", question: null } });
    await wait(1700); // the slow first search would have answered by now
    await act(async () => {
      await slow;
    });
    const s = result.current.state;
    expect(s.status === "done" && s.response.items[0]!.sku).toBe(MILK.question!.options[0]!.sku);
    expect(n).toBe(2);
  }, SLOW_TEST_MS);
});

it("the question has no accessibility violations", async () => {
  await startSearch("milk");
  await question();
  expect(await axe(document.body)).toHaveNoViolations();
});
