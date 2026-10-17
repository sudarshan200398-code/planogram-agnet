import type { Route, SearchResponse, StoreMap } from "../api/types";
import { fixture } from "../test/handlers";
import { layoutFloor, overlap, type Box } from "./mapLayout";

const MAPS: Record<string, StoreMap> = {
  central: fixture("map_central").body as StoreMap,
  riverside: fixture("map_riverside").body as StoreMap,
};
const routeOf = (name: string) => (fixture(name).body as SearchResponse).route!;
const CASES: [string, string, Route][] = [
  ["central", "search_central_bagels", routeOf("search_central_bagels")],
  ["central", "basket_central_route", routeOf("basket_central_route")],
  ["central", "clarify_central_sentence_3", routeOf("clarify_central_sentence_3")],
  ["riverside", "basket_riverside_route", routeOf("basket_riverside_route")],
  ["riverside", "search_riverside_kibble", routeOf("search_riverside_kibble")],
];
// The map's on-screen width: inside the route card on a 360px phone, and the widest it is drawn on desktop.
const WIDTHS_PX = [280, 640];

describe.each(CASES)("%s map, route %s", (store, _name, route) => {
  const map = MAPS[store]!;
  const floors = [...new Set(route.segments.filter((s) => s.lines.length).map((s) => s.floor))];

  it.each(WIDTHS_PX)("at %ipx every label is inside the floor and overlaps no label or marker", (px) => {
    for (const floor of floors) {
      const l = layoutFloor(map, route, floor, (map.bounds.width + 4) / px);
      const labels = [...l.zoneLabels, ...l.markerLabels];
      expect(l.zoneLabels.map((z) => z.text.join(" "))).toEqual(map.zones.filter((z) => z.floor === floor).map((z) => z.label));
      for (const a of labels) {
        expect(a.box.x0, a.text.join(" ")).toBeGreaterThanOrEqual(l.frame.x0);
        expect(a.box.x1, a.text.join(" ")).toBeLessThanOrEqual(l.frame.x1);
        expect(a.box.y0, a.text.join(" ")).toBeGreaterThanOrEqual(l.frame.y0);
        expect(a.box.y1, a.text.join(" ")).toBeLessThanOrEqual(l.frame.y1);
        for (const b of labels) if (a !== b) expect(overlap(a.box, b.box), `${a.text} / ${b.text}`).toBe(0);
        for (const m of l.markers) expect(overlap(a.box, m), `${a.text} over a marker`).toBe(0);
      }
    }
  });

  it.each(WIDTHS_PX)("at %ipx every zone label is next to its marker or joined to it by a leader line", (px) => {
    for (const floor of floors) {
      const l = layoutFloor(map, route, floor, (map.bounds.width + 4) / px);
      for (const z of l.zones) {
        const b = z.label.box;
        const nx = Math.min(Math.max(z.at.x, b.x0), b.x1);
        const ny = Math.min(Math.max(z.at.y, b.y0), b.y1);
        const far = Math.hypot(nx - z.at.x, ny - z.at.y) > l.font * 2.5;
        if (far) expect(z.label.leader, z.label.text.join(" ")).not.toBeNull();
      }
    }
  });
});

it("overlap is the shared area of two boxes", () => {
  const a: Box = { x0: 0, y0: 0, x1: 2, y1: 2 };
  expect(overlap(a, { x0: 1, y0: 1, x1: 3, y1: 3 })).toBe(1);
  expect(overlap(a, { x0: 2, y0: 0, x1: 3, y1: 1 })).toBe(0);
});
