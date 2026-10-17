// Layout for one floor of the route map: where every marker and label goes, in map units.
// Pure (no React) so it can be tested; RouteMap.tsx only draws what this returns.
import type { MapNode, Route, StoreMap } from "../api/types";

export type Box = { x0: number; y0: number; x1: number; y1: number };
/** `leader` joins a label to its marker when the label had to sit further away. */
export type PlacedLabel = { text: string[]; box: Box; bold: boolean; leader: [Point, Point] | null };
export type Point = { x: number; y: number };

export const MAP_PAD = 2; // map units between the floor outline and the edge of the drawing
export const MAP_SIZES_PX = {
  label: 11, // zone label text, on screen, at any map width
  zone: 7, // zone marker square
  stop: 22, // numbered stop circle
  start: 18, // start square
  connector: 18, // floor-change diamond
  gap: 3, // between a marker and its label
} as const;
const CHAR_WIDTH = 0.6; // average glyph width as a share of font size (bold is wider)
const LINE_HEIGHT = 1.15;
const WRAP_AT = 12; // labels longer than this are tried on two lines first

const CONNECTOR_NAME: Record<string, string> = { escalator: "Escalator", elevator: "Lift", stairs: "Stairs" };
export const connectorName = (type: string) => CONNECTOR_NAME[type] ?? type.charAt(0).toUpperCase() + type.slice(1);

export type FloorChange = { type: string; fromFloor: number; toFloor: number; from: MapNode; to: MapNode };

export function overlap(a: Box, b: Box): number {
  const w = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0);
  const h = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
  return w > 0 && h > 0 ? w * h : 0;
}
const around = (p: Point, half: number): Box => ({ x0: p.x - half, y0: p.y - half, x1: p.x + half, y1: p.y + half });
const grow = (b: Box, by: number): Box => ({ x0: b.x0 - by, y0: b.y0 - by, x1: b.x1 + by, y1: b.y1 + by });

/** Ways to write a label: one line, or split in two at the most balanced word break. */
export function labelWrappings(label: string): string[][] {
  const words = label.split(" ");
  const options: string[][] = [[label]];
  if (words.length > 1) {
    let best: string[] = [];
    for (let i = 1; i < words.length; i++) {
      const pair = [words.slice(0, i).join(" "), words.slice(i).join(" ")];
      if (!best.length || Math.max(...pair.map((s) => s.length)) < Math.max(...best.map((s) => s.length))) best = pair;
    }
    options.push(best);
  }
  return label.length > WRAP_AT ? options.reverse() : options;
}

/** Floors in the order the route visits them, keeping only floors with route lines. */
export function routeFloors(route: Route, nodes: Map<string, MapNode>): number[] {
  const drawn = new Set(route.segments.filter((s) => s.lines.length).map((s) => s.floor));
  const visited = route.path.map((id) => nodes.get(id)?.floor).filter((f): f is number => f !== undefined);
  return [...new Set([...visited, ...route.segments.map((s) => s.floor)])].filter((f) => drawn.has(f));
}

/** Where the route moves between floors: consecutive path nodes on different floors. */
export function floorChanges(route: Route, nodes: Map<string, MapNode>): FloorChange[] {
  const changes: FloorChange[] = [];
  for (let i = 1; i < route.path.length; i++) {
    const from = nodes.get(route.path[i - 1]!);
    const to = nodes.get(route.path[i]!);
    if (from && to && from.floor !== to.floor) changes.push({ type: from.type, fromFloor: from.floor, toFloor: to.floor, from, to });
  }
  return changes;
}

/** Places labels one by one at the free spot nearest their marker. */
class Placer {
  placed: Box[] = [];
  constructor(
    private frame: Box,
    private hard: Box[],
    private soft: Box[],
    private font: number,
    private margin: number,
  ) {}

  private size(lines: string[], bold: boolean) {
    const longest = Math.max(...lines.map((l) => l.length));
    return { w: longest * this.font * (bold ? CHAR_WIDTH * 1.08 : CHAR_WIDTH), h: lines.length * this.font * LINE_HEIGHT };
  }

  private clamp(b: Box): Box {
    const dx = b.x0 < this.frame.x0 ? this.frame.x0 - b.x0 : b.x1 > this.frame.x1 ? this.frame.x1 - b.x1 : 0;
    const dy = b.y0 < this.frame.y0 ? this.frame.y0 - b.y0 : b.y1 > this.frame.y1 ? this.frame.y1 - b.y1 : 0;
    return { x0: b.x0 + dx, y0: b.y0 + dy, x1: b.x1 + dx, y1: b.y1 + dy };
  }

  place(at: Point, clearance: number, wrappings: string[][], bold: boolean): PlacedLabel {
    let best: { score: number; label: PlacedLabel } | null = null;
    wrappings.forEach((text, wi) => {
      const { w, h } = this.size(text, bold);
      for (const [di, d] of [clearance, clearance + this.font, clearance + 2.5 * this.font, clearance + 4 * this.font].entries()) {
        const k = d * 0.7;
        const spots: Box[] = [
          { x0: at.x - w / 2, y0: at.y + d, x1: at.x + w / 2, y1: at.y + d + h }, // below
          { x0: at.x - w / 2, y0: at.y - d - h, x1: at.x + w / 2, y1: at.y - d }, // above
          { x0: at.x + d, y0: at.y - h / 2, x1: at.x + d + w, y1: at.y + h / 2 }, // right
          { x0: at.x - d - w, y0: at.y - h / 2, x1: at.x - d, y1: at.y + h / 2 }, // left
          { x0: at.x + k, y0: at.y + k, x1: at.x + k + w, y1: at.y + k + h },
          { x0: at.x - k - w, y0: at.y + k, x1: at.x - k, y1: at.y + k + h },
          { x0: at.x + k, y0: at.y - k - h, x1: at.x + k + w, y1: at.y - k },
          { x0: at.x - k - w, y0: at.y - k - h, x1: at.x - k, y1: at.y - k },
          // above and below, slid sideways (for crowded rows of zones)
          ...[-1, -0.5, 0.5, 1].flatMap((f) => [
            { x0: at.x - w / 2 + f * w, y0: at.y + d, x1: at.x + w / 2 + f * w, y1: at.y + d + h },
            { x0: at.x - w / 2 + f * w, y0: at.y - d - h, x1: at.x + w / 2 + f * w, y1: at.y - d },
          ]),
        ];
        spots.forEach((spot, si) => {
          const box = this.clamp(spot);
          const near = grow(box, this.margin);
          const hard = [...this.hard, ...this.placed].reduce((s, o) => s + overlap(near, o), 0);
          const soft = this.soft.reduce((s, o) => s + overlap(box, o), 0);
          const score = hard * 1000 + soft + di * 0.5 + wi * 0.2 + si * 0.01;
          if (!best || score < best.score) best = { score, label: { text, box, bold, leader: null } };
        });
      }
    });
    const label: PlacedLabel = best!.label;
    // Nearest point of the label to its marker; far labels get a leader line so they can't be misread.
    const near = { x: Math.min(Math.max(at.x, label.box.x0), label.box.x1), y: Math.min(Math.max(at.y, label.box.y0), label.box.y1) };
    if (Math.hypot(near.x - at.x, near.y - at.y) > clearance + this.font * 0.6) label.leader = [{ x: at.x, y: at.y }, near];
    this.placed.push(label.box);
    return label;
  }
}

export interface FloorLayout {
  floor: number;
  frame: Box; // the floor outline; labels stay inside it
  viewBox: Box;
  unit: number; // map units per screen pixel
  font: number;
  walks: [Point, Point][];
  routeLines: [Point, Point][];
  zones: { id: string; at: Point; label: PlacedLabel }[];
  zoneLabels: PlacedLabel[];
  start: { at: Point; label: PlacedLabel } | null;
  connectors: { id: string; name: string; at: Point; label: PlacedLabel }[];
  stops: { order: number; sku: string; at: Point }[];
  markerLabels: PlacedLabel[];
  markers: Box[]; // every marker's box: start, stops, connectors, zone squares
}

/** Everything needed to draw one floor at a given scale (`unit` = map units per screen pixel). */
export function layoutFloor(map: StoreMap, route: Route, floor: number, unit: number): FloorLayout {
  const nodes = new Map(map.nodes.map((n) => [n.id, n]));
  const px = (n: number) => n * unit;
  const font = px(MAP_SIZES_PX.label);
  const { width: w, height: h } = map.bounds;
  const frame: Box = { x0: -MAP_PAD / 2, y0: -MAP_PAD / 2, x1: w + MAP_PAD / 2, y1: h + MAP_PAD / 2 };
  const viewBox: Box = { x0: -MAP_PAD, y0: -MAP_PAD, x1: w + MAP_PAD, y1: h + MAP_PAD };
  const pt = (xy: number[] | undefined): Point => ({ x: xy?.[0] ?? 0, y: xy?.[1] ?? 0 });

  const walks = map.edges
    .filter((e) => e.floor === floor && nodes.has(e.a) && nodes.has(e.b))
    .map((e) => [nodes.get(e.a)!, nodes.get(e.b)!] as [Point, Point]);
  const routeLines = route.segments
    .filter((s) => s.floor === floor)
    .flatMap((s) => s.lines.map(([a, b]) => [pt(a), pt(b)] as [Point, Point]));

  // Markers first: they never move, labels go around them.
  const startNode = nodes.get(route.start_node) ?? nodes.get(route.path[0] ?? "");
  const startAt = startNode?.floor === floor ? { x: startNode.x, y: startNode.y } : null;
  const changes = floorChanges(route, nodes);
  const connectorNodes = changes
    .flatMap((c) => [c.from, c.to])
    .filter((n, i, all) => n.floor === floor && all.findIndex((m) => m.id === n.id) === i);
  const perNode = new Map<string, number>();
  const stops = route.stops
    .filter((s) => s.floor === floor && s.node_id && nodes.has(s.node_id))
    .map((s) => {
      const n = nodes.get(s.node_id!)!;
      const k = perNode.get(n.id) ?? 0; // several stops at one place sit side by side
      perNode.set(n.id, k + 1);
      return { order: s.order, sku: s.sku, at: { x: n.x + px(MAP_SIZES_PX.stop + 2) * k, y: n.y } };
    });
  const zoneNodes = map.zones.filter((z) => z.floor === floor && nodes.has(z.node_id)).map((z) => ({ z, n: nodes.get(z.node_id)! }));

  const markers: Box[] = [
    ...zoneNodes.map(({ n }) => around(n, px(MAP_SIZES_PX.zone / 2))),
    ...stops.map((s) => around(s.at, px(MAP_SIZES_PX.stop / 2))),
    ...connectorNodes.map((n) => around(n, px((MAP_SIZES_PX.connector / 2) * Math.SQRT2))),
    ...(startAt ? [around(startAt, px(MAP_SIZES_PX.start / 2))] : []),
  ];
  // The route line is a soft obstacle: labels avoid covering it when they can.
  const routeDots: Box[] = routeLines.flatMap(([a, b]) => {
    const steps = Math.max(1, Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / px(4)));
    return Array.from({ length: steps + 1 }, (_, i) => around({ x: a.x + ((b.x - a.x) * i) / steps, y: a.y + ((b.y - a.y) * i) / steps }, px(3)));
  });
  const placer = new Placer(frame, markers, routeDots, font, px(1));
  const clearanceAt = (p: Point, base: number) =>
    Math.max(base, ...stops.filter((s) => Math.hypot(s.at.x - p.x, s.at.y - p.y) < px(4)).map(() => MAP_SIZES_PX.stop / 2)) * unit +
    px(MAP_SIZES_PX.gap);

  const start = startAt ? { at: startAt, label: placer.place(startAt, px(MAP_SIZES_PX.start / 2 + MAP_SIZES_PX.gap), [["Start"]], true) } : null;
  const connectors = connectorNodes.map((n) => {
    const name = connectorName(n.type);
    return { id: n.id, name, at: { x: n.x, y: n.y }, label: placer.place(n, px(MAP_SIZES_PX.connector * 0.75 + MAP_SIZES_PX.gap), [[name]], true) };
  });
  const zones = zoneNodes.map(({ z, n }) => ({
    id: z.node_id,
    at: { x: n.x, y: n.y },
    label: placer.place(n, clearanceAt(n, MAP_SIZES_PX.zone / 2), labelWrappings(z.label), false),
  }));

  return {
    floor,
    frame,
    viewBox,
    unit,
    font,
    walks,
    routeLines,
    zones,
    zoneLabels: zones.map((z) => z.label),
    start,
    connectors,
    stops,
    markerLabels: [...(start ? [start.label] : []), ...connectors.map((c) => c.label)],
    markers,
  };
}
