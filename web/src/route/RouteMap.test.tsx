import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http } from "msw";
import { App } from "../App";
import type { Route, SearchResponse, StoreMap } from "../api/types";
import { STORAGE_KEYS } from "../config";
import { fixture, reply } from "../test/handlers";
import { expectNoRouteUnderSearch } from "../test/noRoute";
import { server } from "../test/server";
import { RouteMap } from "./RouteMap";

const MAP_CENTRAL = fixture("map_central").body as StoreMap;
const MAP_RIVERSIDE = fixture("map_riverside").body as StoreMap;
const routeOf = (name: string) => (fixture(name).body as SearchResponse).route!;
const ONE_FLOOR = routeOf("search_central_bagels");
const TWO_FLOORS = routeOf("basket_central_route");
const RIVERSIDE = routeOf("search_riverside_kibble");

const drawnFloors = (r: Route) => r.segments.filter((s) => s.lines.length).map((s) => s.floor);
const maps = () => screen.queryAllByRole("img", { name: /^Map of Level/ });

describe("RouteMap", () => {
  it("one-floor route: draws only that floor", () => {
    expect(drawnFloors(ONE_FLOOR)).toEqual([1]);
    render(<RouteMap map={MAP_CENTRAL} route={ONE_FLOOR} />);
    expect(maps()).toHaveLength(1);
    const m = maps()[0]!;
    expect(m).toHaveAccessibleName(expect.stringContaining(`starts at ${ONE_FLOOR.start_label}`));
    expect(m).toHaveAccessibleName(expect.stringContaining(`stop 1 ${ONE_FLOOR.stops[0]!.zone}`));
    expect(screen.queryByTestId("connector-marker")).not.toBeInTheDocument();
  });

  it("two-floor route: one map per floor, in route order, linked by the floor change", () => {
    render(<RouteMap map={MAP_CENTRAL} route={TWO_FLOORS} />);
    const [first, second] = maps();
    expect(maps()).toHaveLength(2);
    expect(first).toHaveAccessibleName(expect.stringMatching(/^Map of Level 1\. .*then takes the escalator to Level 2\.$/));
    expect(second).toHaveAccessibleName(expect.stringMatching(/^Map of Level 2\. Arrives by escalator from Level 1.*ends here\.$/));
    // The escalator is marked on both floors, with its name (never colour alone).
    for (const m of [first!, second!]) {
      expect(within(m).getByTestId("connector-marker")).toHaveTextContent("Escalator");
    }
  });

  it("draws the start marker once, on the floor where the route starts", () => {
    render(<RouteMap map={MAP_CENTRAL} route={TWO_FLOORS} />);
    const [first, second] = maps();
    expect(within(first!).getByTestId("start-marker")).toHaveTextContent("Start");
    expect(within(second!).queryByTestId("start-marker")).not.toBeInTheDocument();
  });

  it("numbers the stops on their own floors, matching the stop list", () => {
    render(<RouteMap map={MAP_CENTRAL} route={TWO_FLOORS} />);
    const [first, second] = maps();
    const numbersOn = (m: HTMLElement) => within(m).queryAllByTestId("stop-marker").map((s) => s.textContent);
    expect(numbersOn(first!)).toEqual(TWO_FLOORS.stops.filter((s) => s.floor === 1).map((s) => String(s.order)));
    expect(numbersOn(second!)).toEqual(TWO_FLOORS.stops.filter((s) => s.floor === 2).map((s) => String(s.order)));
    const legend = screen.getByRole("list", { name: "Stops" });
    expect(within(legend).getAllByRole("listitem").map((li) => li.textContent)).toEqual(
      TWO_FLOORS.stops.map((s) => expect.stringContaining(`${s.order}${s.name}`)),
    );
  });

  it("labels every zone of each drawn floor", () => {
    render(<RouteMap map={MAP_CENTRAL} route={TWO_FLOORS} />);
    const [first, second] = maps();
    for (const [m, floor] of [[first!, 1], [second!, 2]] as const) {
      const labels = within(m).getAllByTestId("zone-label").map((t) => t.textContent);
      expect(labels).toEqual(MAP_CENTRAL.zones.filter((z) => z.floor === floor).map((z) => z.label));
    }
  });

  it("draws the route line from the API's segments, per floor", () => {
    render(<RouteMap map={MAP_CENTRAL} route={TWO_FLOORS} />);
    expect(maps()).toHaveLength(2);
    maps().forEach((m, i) => {
      const lines = TWO_FLOORS.segments.filter((s) => s.lines.length)[i]!.lines;
      expect(within(m).getAllByTestId("route-line")).toHaveLength(lines.length);
    });
  });

  it("works for another store's map (Riverside, two floors)", () => {
    render(<RouteMap map={MAP_RIVERSIDE} route={RIVERSIDE} />);
    expect(maps()).toHaveLength(drawnFloors(RIVERSIDE).length);
    expect(maps()[0]).toHaveAccessibleName(expect.stringContaining(`starts at ${RIVERSIDE.start_label}`));
  });

  it("draws nothing when the route has no segments", () => {
    const { container } = render(<RouteMap map={MAP_CENTRAL} route={{ ...ONE_FLOOR, segments: [] }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<RouteMap map={MAP_CENTRAL} route={TWO_FLOORS} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("the map in the app", () => {
  async function start() {
    window.history.replaceState(null, "", "/?store=central");
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("combobox", { name: "Store" });
    return user;
  }
  /** The recorded two-floor list, opened in its sheet. */
  async function openRecordedList() {
    const BASKET = fixture("basket_central_route");
    const names = (BASKET.body as SearchResponse).items.map((i) => i.name!);
    const lines = (BASKET.request.body as { items: { sku: string; qty: number }[] }).items;
    localStorage.setItem(
      STORAGE_KEYS.list("central"),
      JSON.stringify(lines.map((b, i) => ({ sku: b.sku, name: names[i]!, qty: b.qty, image_url: null, place: null }))),
    );
    const user = await start();
    await user.click(screen.getByRole("button", { name: /^Shopping list/ }));
    return { user, sheet: screen.getByRole("dialog", { name: "Shopping list" }) };
  }

  it("is not shown under a typed search, though the response carries a route", async () => {
    expect(ONE_FLOOR).not.toBeNull();
    const user = await start();
    await user.type(screen.getByRole("combobox", { name: "Search products" }), "Daily Bake Plain Bagels 4 pack{Enter}");
    await screen.findByTestId("result-card");
    expect(maps()).toHaveLength(0);
    expectNoRouteUnderSearch();
  });

  it("is shown under the shopping list route", async () => {
    const { user, sheet } = await openRecordedList();
    await user.click(within(sheet).getByRole("button", { name: "Find my route" }));
    expect(await within(sheet).findAllByRole("img", { name: /^Map of Level/ })).toHaveLength(2);
    expect(await axe(sheet)).toHaveNoViolations();
  });

  it("no route, no map", async () => {
    const user = await start();
    await user.type(screen.getByRole("combobox", { name: "Search products" }), "zzqx wobble gadget{Enter}");
    await screen.findAllByTestId("result-card");
    expect(screen.queryByRole("region", { name: "Your route" })).not.toBeInTheDocument();
    expect(maps()).toHaveLength(0);
  });

  it("if the map can't load, the list's step list still works and says so", async () => {
    server.use(http.get("*/api/stores/central/map", () => reply("error_rate_limited")));
    const { user, sheet } = await openRecordedList();
    await user.click(within(sheet).getByRole("button", { name: "Find my route" }));
    const route = await within(sheet).findByRole("region", { name: "Your route" });
    expect(await within(route).findByText("The map isn't available right now. The steps above show the way.")).toBeInTheDocument();
    expect(within(route).getAllByRole("listitem").length).toBeGreaterThan(0);
  });
});
