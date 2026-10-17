import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";
import { App } from "./App";
import { reply } from "./test/handlers";
import { server } from "./test/server";

async function renderApp(url = "/") {
  window.history.replaceState(null, "", url);
  const user = userEvent.setup();
  render(<App />);
  const select = await screen.findByRole("combobox", { name: "Store" });
  return { user, select };
}

async function search(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(screen.getByRole("combobox", { name: "Search products" }), text);
  await user.click(screen.getByRole("button", { name: "Search" }));
}

describe("store selector", () => {
  it("loads the stores, picks the first and remembers it in the URL and storage", async () => {
    const { select } = await renderApp();
    expect(select).toHaveValue("central");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Central Store", "Riverside Market"]);
    expect(new URL(window.location.href).searchParams.get("store")).toBe("central");
    expect(window.localStorage.getItem("superfind.store")).toBe("central");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Find anything in Central Store");
  });

  it("switches store and every search goes to that store", async () => {
    const { user, select } = await renderApp();
    await user.selectOptions(select, "riverside");
    expect(new URL(window.location.href).searchParams.get("store")).toBe("riverside");
    expect(window.localStorage.getItem("superfind.store")).toBe("riverside");
    await search(user, "i am near the fresh market, Pebble Pet Puppy Kibble 1 kg");
    expect(await screen.findByText("Pebble Pet Puppy Kibble 1 kg")).toBeInTheDocument();
  });

  it("opens the store from the URL, ahead of the remembered one", async () => {
    window.localStorage.setItem("superfind.store", "central");
    const { select } = await renderApp("/?store=riverside");
    expect(select).toHaveValue("riverside");
  });

  it("falls back to the first store if the remembered one is gone", async () => {
    window.localStorage.setItem("superfind.store", "closed-store");
    const { select } = await renderApp();
    expect(select).toHaveValue("central");
  });

  it("resets to the first store when the API says the store is not found", async () => {
    const { user, select } = await renderApp("/?store=riverside");
    server.use(http.post("*/api/stores/riverside/search", () => reply("error_store_not_found")));
    await search(user, "anything");
    await waitFor(() => expect(select).toHaveValue("central"));
    expect(screen.getByRole("status")).toHaveTextContent(/switched to the first store/i);
  });

  it("shows a friendly error with a retry if the stores can't load", async () => {
    server.use(http.get("*/api/stores", () => HttpResponse.error()));
    window.history.replaceState(null, "", "/");
    render(<App />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Can't reach the store");
    server.resetHandlers();
    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("combobox", { name: "Store" })).toHaveValue("central");
  });
});

describe("search and result cards", () => {
  it("shows an in-stock product with picture, price, stock and location", async () => {
    const { user } = await renderApp();
    await search(user, "Daily Bake Plain Bagels 4 pack");
    const card = (await screen.findAllByTestId("result-card"))[0]!;
    expect(within(card).getByRole("heading")).toHaveTextContent("Daily Bake Plain Bagels 4 pack");
    expect(card).toHaveTextContent("₹94");
    expect(card).toHaveTextContent("In stock · 68");
    expect(card).toHaveTextContent("Level 1 · Bakery · Bay A · Shelf 2");
    const img = card.querySelector("img")!;
    expect(img).toHaveAttribute("src", "/api/stores/central/products/BAK-BAG-009/image");
    expect(img).toHaveAttribute("loading", "lazy");
  });

  it("marks out-of-stock products clearly in text, not just colour", async () => {
    const { user } = await renderApp();
    await search(user, "ArtBox Watercolour Paints 12 pack");
    const card = await screen.findByTestId("result-card");
    expect(card).toHaveAttribute("data-status", "unavailable");
    expect(within(card).getByText("Out of stock")).toBeInTheDocument();
  });

  it("explains a product that isn't in the store", async () => {
    const { user } = await renderApp();
    await search(user, "zzqx wobble gadget");
    expect(await screen.findByText("Not sold at Central Store")).toBeInTheDocument(); // 3B wording
  });

  it("hides the price cleanly when the store has none", async () => {
    const { user } = await renderApp();
    server.use(
      http.post("*/api/stores/central/search", async () => {
        const body = structuredClone((await import("./api/fixtures/search_central_bagels.json")).default.body);
        body.items[0]!.price = null as unknown as number;
        return HttpResponse.json(body);
      }),
    );
    await search(user, "bagels");
    const card = await screen.findByTestId("result-card");
    expect(card).not.toHaveTextContent("₹");
    expect(card).toHaveTextContent("In stock · 68");
  });

  it("shows a fallback tile if the picture fails to load", async () => {
    const { user } = await renderApp();
    await search(user, "Daily Bake Plain Bagels 4 pack");
    const card = await screen.findByTestId("result-card");
    card.querySelector("img")!.dispatchEvent(new Event("error"));
    expect(await within(card).findByTestId("image-fallback")).toHaveTextContent("DB");
  });

  it("shows a friendly message and the request id when the API is busy (429)", async () => {
    const { user } = await renderApp();
    server.use(http.post("*/api/stores/central/search", () => reply("error_rate_limited")));
    await search(user, "milk");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Lots of searches right now");
    expect(alert).toHaveTextContent("Please wait about 60 seconds");
    expect(alert).toHaveTextContent("Reference: fixture-error_rate_limited");
    expect(alert).not.toHaveTextContent(/RATE_LIMITED|Too many requests/);
  });

  it("has no accessibility violations with results on screen", async () => {
    const { user } = await renderApp();
    await search(user, "Daily Bake Plain Bagels 4 pack");
    await screen.findByTestId("result-card");
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
