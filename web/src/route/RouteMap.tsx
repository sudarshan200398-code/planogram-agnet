import { useLayoutEffect, useRef, useState } from "react";
import type { Route, StoreMap } from "../api/types";
import { connectorName, floorChanges, layoutFloor, MAP_PAD, MAP_SIZES_PX, routeFloors, type FloorChange, type PlacedLabel } from "./mapLayout";
import "./map.css";

/**
 * Inline SVG maps of the floors a route touches, stacked (they stay readable at 360px without tabs).
 * Presentational only: give it the store map and the route; positions come from mapLayout.ts.
 * Phase 3 can add interaction (highlight a step, zoom, guided walk) on top of these props.
 */
export interface RouteMapProps {
  map: StoreMap;
  route: Route;
}

const FALLBACK_WIDTH_PX = 320; // before the first measurement (and in tests)
export const MAP_MAX_WIDTH_PX = 640; // matches .sf-map__svg max-width

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => entry && setWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, width: Math.min(width || FALLBACK_WIDTH_PX, MAP_MAX_WIDTH_PX) };
}

function describeFloor(floor: number, route: Route, isStart: boolean, arrive?: FloorChange, leave?: FloorChange): string {
  const opening = isStart
    ? `The route starts at ${route.start_label}`
    : arrive
      ? `Arrives by ${connectorName(arrive.type).toLowerCase()} from Level ${arrive.fromFloor}`
      : "The route continues here";
  const stops = route.stops.filter((s) => s.floor === floor).map((s) => `stop ${s.order} ${s.zone ?? s.name}`);
  const ending = leave ? `then takes the ${connectorName(leave.type).toLowerCase()} to Level ${leave.toFloor}.` : "and ends here.";
  return `Map of Level ${floor}. ${[opening, ...stops, ending].join(", ")}`;
}

function Label({ label, font, unit, testId }: { label: PlacedLabel; font: number; unit: number; testId?: string }) {
  const { box, text } = label;
  return (
    <text
      data-testid={testId}
      className={`sf-map__label ${label.bold ? "sf-map__label--strong" : ""}`}
      x={(box.x0 + box.x1) / 2}
      y={box.y0 + font * 0.9}
      fontSize={font}
      textAnchor="middle"
      strokeWidth={3 * unit}
    >
      {text.map((t, i) => (
        <tspan key={i} x={(box.x0 + box.x1) / 2} dy={i === 0 ? 0 : font * 1.15}>
          {i < text.length - 1 ? `${t} ` : t}
        </tspan>
      ))}
    </text>
  );
}

function FloorMap({ map, route, floor, unit, changes }: { map: StoreMap; route: Route; floor: number; unit: number; changes: FloorChange[] }) {
  const l = layoutFloor(map, route, floor, unit);
  const px = (n: number) => n * unit;
  const vb = l.viewBox;
  const line = (key: string | number, [a, b]: [{ x: number; y: number }, { x: number; y: number }], testId?: string) => (
    <line key={key} data-testid={testId} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
  );
  return (
    <figure className="sf-map__floor">
      <figcaption className="sf-map__caption">Level {floor}</figcaption>
      <svg
        className="sf-map__svg"
        role="img"
        aria-label={describeFloor(floor, route, !!l.start, changes.find((c) => c.toFloor === floor), changes.find((c) => c.fromFloor === floor))}
        viewBox={`${vb.x0} ${vb.y0} ${vb.x1 - vb.x0} ${vb.y1 - vb.y0}`}
      >
        <rect className="sf-map__outline" x={l.frame.x0} y={l.frame.y0} width={l.frame.x1 - l.frame.x0} height={l.frame.y1 - l.frame.y0} rx={MAP_PAD * 0.6} strokeWidth={px(1.5)} />
        <g className="sf-map__walks" strokeWidth={px(3)}>
          {l.walks.map((wk, i) => line(i, wk))}
        </g>
        <g className="sf-map__zones">
          {l.zones.map((z) => (
            <rect key={z.id} className="sf-map__zone" x={z.at.x - px(MAP_SIZES_PX.zone / 2)} y={z.at.y - px(MAP_SIZES_PX.zone / 2)} width={px(MAP_SIZES_PX.zone)} height={px(MAP_SIZES_PX.zone)} rx={px(1.5)} />
          ))}
        </g>
        <g className="sf-map__route-casing" strokeWidth={px(8)}>
          {l.routeLines.map((r, i) => line(i, r))}
        </g>
        <g className="sf-map__route" strokeWidth={px(4)}>
          {l.routeLines.map((r, i) => line(i, r, "route-line"))}
        </g>
        <g className="sf-map__leaders" strokeWidth={px(1.25)}>
          {[...l.zoneLabels, ...l.markerLabels].map((lb, i) => (lb.leader ? line(`leader-${i}`, lb.leader) : null))}
        </g>
        {l.zones.map((z) => (
          <Label key={z.id} label={z.label} font={l.font} unit={unit} testId="zone-label" />
        ))}
        {l.connectors.map((c) => {
          const s = px(MAP_SIZES_PX.connector / 2);
          return (
            <g key={c.id} data-testid="connector-marker" className="sf-map__connector">
              <rect x={c.at.x - s} y={c.at.y - s} width={2 * s} height={2 * s} transform={`rotate(45 ${c.at.x} ${c.at.y})`} strokeWidth={px(2)} />
              <Label label={c.label} font={l.font} unit={unit} />
            </g>
          );
        })}
        {l.start ? (
          <g data-testid="start-marker" className="sf-map__start">
            <rect
              x={l.start.at.x - px(MAP_SIZES_PX.start / 2)}
              y={l.start.at.y - px(MAP_SIZES_PX.start / 2)}
              width={px(MAP_SIZES_PX.start)}
              height={px(MAP_SIZES_PX.start)}
              rx={px(3)}
              strokeWidth={px(2.5)}
            />
            <Label label={l.start.label} font={l.font} unit={unit} />
          </g>
        ) : null}
        {l.stops.map((s) => (
          <g key={`${s.order}-${s.sku}`} data-testid="stop-marker" className="sf-map__stop">
            <circle cx={s.at.x} cy={s.at.y} r={px(MAP_SIZES_PX.stop / 2)} strokeWidth={px(2)} />
            <text x={s.at.x} y={s.at.y + px(4.5)} fontSize={px(13)} textAnchor="middle">
              {s.order}
            </text>
          </g>
        ))}
      </svg>
    </figure>
  );
}

export function RouteMap({ map, route }: RouteMapProps) {
  const { ref, width } = useWidth();
  const nodes = new Map(map.nodes.map((n) => [n.id, n]));
  const floors = routeFloors(route, nodes);
  if (!floors.length) return null;
  const changes = floorChanges(route, nodes);
  const unit = (map.bounds.width + 2 * MAP_PAD) / width;
  return (
    <div className="sf-map" ref={ref}>
      {floors.map((f) => (
        <FloorMap key={f} map={map} route={route} floor={f} unit={unit} changes={changes} />
      ))}
      {route.stops.length ? (
        <ol className="sf-map__stops" aria-label="Stops">
          {route.stops.map((s) => (
            <li key={`${s.order}-${s.sku}`}>
              <span className="sf-map__stop-number" aria-hidden="true">
                {s.order}
              </span>
              {s.name}
              <span className="sf-map__stop-place">{[s.floor != null ? `Level ${s.floor}` : null, s.zone].filter(Boolean).join(" · ")}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
