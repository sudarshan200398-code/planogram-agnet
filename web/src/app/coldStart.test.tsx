import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";
import { App } from "../App";
import { REQUEST_TIMEOUT_MS, SLOW_REQUEST_MS } from "../config";
import { reply } from "../test/handlers";
import { server } from "../test/server";

// The free API host sleeps when idle; its first answer can take 30 to 60 seconds.
const WAKING = "Waking up the store server, this can take up to a minute.";
const BAGELS = "Daily Bake Plain Bagels 4 pack";

/** A response the test releases by hand. */
function gate() {
  let open!: () => void;
  const opened = new Promise<void>((r) => (open = r));
  return { open, opened };
}
const never = () => new Promise<never>(() => {});
const advance = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));
const header = () => screen.getByRole("banner");
const results = () => screen.getByRole("region", { name: "Results" });

function countStores() {
  const calls = { stores: 0 };
  server.events.on("request:start", ({ request }) => {
    if (new URL(request.url).pathname.endsWith("/stores")) calls.stores++;
  });
  return calls;
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  window.history.replaceState(null, "", "/?store=central");
});
afterEach(() => vi.useRealTimers());

describe("store list", () => {
  it(`says the server is waking up after ${SLOW_REQUEST_MS / 1000} s, and the message goes on success`, async () => {
    const g = gate();
    server.use(
      http.get("*/api/stores", async () => {
        await g.opened;
        return reply("stores");
      }),
    );
    render(<App />);
    await advance(SLOW_REQUEST_MS - 500);
    expect(screen.queryByText(WAKING)).not.toBeInTheDocument(); // not for a normal short wait
    await advance(1000);
    const note = within(header()).getByRole("status");
    expect(note).toHaveTextContent(WAKING);
    expect(await axe(header())).toHaveNoViolations();

    g.open();
    expect(await screen.findByRole("combobox", { name: "Store" })).toBeInTheDocument();
    expect(screen.queryByText(WAKING)).not.toBeInTheDocument();
  });

  it("is tried once more after a failure, without showing an error", async () => {
    const calls = countStores();
    let first = true;
    server.use(
      http.get("*/api/stores", () => {
        if (first) {
          first = false;
          return HttpResponse.error();
        }
        return reply("stores");
      }),
    );
    render(<App />);
    expect(await screen.findByRole("combobox", { name: "Store" })).toBeInTheDocument();
    expect(calls.stores).toBe(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("after a timeout and one more try, shows a friendly error with a retry button that works", async () => {
    const calls = countStores();
    let answer = false;
    server.use(http.get("*/api/stores", () => (answer ? reply("stores") : never())));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<App />);
    await advance(REQUEST_TIMEOUT_MS + 100);
    expect(calls.stores).toBe(2); // the one retry
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await advance(REQUEST_TIMEOUT_MS + 100);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The store server is taking too long");
    expect(alert).toHaveTextContent("It may still be waking up. Please try again.");
    expect(alert).not.toHaveTextContent(/TIMEOUT|abort|signal|Error/);
    expect(screen.queryByText(WAKING)).not.toBeInTheDocument();
    expect(calls.stores).toBe(2);

    answer = true;
    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("combobox", { name: "Store" })).toBeInTheDocument();
  });
});

describe("search", () => {
  async function ready() {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<App />);
    await screen.findByRole("combobox", { name: "Store" });
    return user;
  }
  async function search(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole("combobox", { name: "Search products" }));
    await user.paste(BAGELS);
    await user.keyboard("{Enter}");
  }

  it("says the server is waking up in the results while a search is slow, and the message goes on success", async () => {
    const g = gate();
    server.use(
      http.post("*/api/stores/central/search", async () => {
        await g.opened;
        return reply("search_central_bagels");
      }),
    );
    const user = await ready();
    await search(user);
    await advance(SLOW_REQUEST_MS - 500);
    expect(screen.queryByText(WAKING)).not.toBeInTheDocument();
    await advance(1000);
    expect(within(results()).getByRole("status")).toHaveTextContent(WAKING);
    expect(within(header()).queryByText(WAKING)).not.toBeInTheDocument();

    g.open();
    expect(await screen.findByTestId("result-card")).toBeInTheDocument();
    expect(screen.queryByText(WAKING)).not.toBeInTheDocument();
  });

  it("a search that times out shows the friendly error, and Try again searches again", async () => {
    let answer = false;
    server.use(http.post("*/api/stores/central/search", () => (answer ? reply("search_central_bagels") : never())));
    const user = await ready();
    await search(user);
    await advance(REQUEST_TIMEOUT_MS + 100);

    const alert = await within(results()).findByRole("alert");
    expect(alert).toHaveTextContent("The store server is taking too long");
    expect(screen.queryByText(WAKING)).not.toBeInTheDocument();
    answer = true;
    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByTestId("result-card")).toBeInTheDocument());
  });
});
