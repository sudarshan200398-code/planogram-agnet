import { useId, useState, type ReactElement } from "react";
import type { Route, RouteStep } from "../api/types";
import { ElevatorIcon, EscalatorIcon, PinIcon, StairsIcon, WalkIcon } from "../components/icons";
import { Card } from "../components/ui";
import "./route.css";

/** The API names its step icons after Material icons; map them to ours, with a readable label. */
const STEP_ICON: Record<string, { icon: ReactElement; label: string }> = {
  directions_walk: { icon: <WalkIcon />, label: "Walk" },
  stairs: { icon: <StairsIcon />, label: "Stairs" },
  escalator: { icon: <EscalatorIcon />, label: "Escalator" },
  elevator: { icon: <ElevatorIcon />, label: "Lift" },
  location_on: { icon: <PinIcon />, label: "Arrive" },
};

function stepIcon(step: RouteStep) {
  return STEP_ICON[step.icon] ?? (step.kind === "arrive" ? STEP_ICON.location_on! : STEP_ICON.directions_walk!);
}

export function routeSummary(route: Route): string {
  const metres = Math.round(route.total_distance_m);
  const floors = route.floor_changes === 1 ? "1 floor change" : `${route.floor_changes} floor changes`;
  return `${metres} m · ${floors}`;
}

/** "Your route": totals, then numbered steps. Collapsed by default under a search, open for the list route. */
export function RouteSteps({ route, defaultOpen = false }: { route: Route; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const listId = useId();
  return (
    <Card className="sf-route" aria-labelledby={`${listId}-title`}>
      <div className="sf-route__head">
        <div>
          <h2 id={`${listId}-title`} className="sf-route__title">
            Your route
          </h2>
          <p className="sf-route__summary">
            From {route.start_label} · {routeSummary(route)}
            {route.accessible_only ? " · step-free" : ""}
          </p>
        </div>
        <button type="button" className="sf-route__toggle" aria-expanded={open} aria-controls={listId} onClick={() => setOpen((o) => !o)}>
          {open ? "Hide steps" : `Show ${route.steps.length} steps`}
        </button>
      </div>
      <div className="sf-route__totals" aria-hidden={!open} hidden={!open}>
        <p>
          <strong>{Math.round(route.total_distance_m)} m</strong>
          <span>walking</span>
        </p>
        <p>
          <strong>{route.floor_changes}</strong>
          <span>{route.floor_changes === 1 ? "floor change" : "floor changes"}</span>
        </p>
      </div>
      <ol id={listId} className="sf-route__steps" hidden={!open}>
        {route.steps.map((s) => {
          const { icon, label } = stepIcon(s);
          return (
            <li key={s.number} className={`sf-step sf-step--${s.kind}`}>
              <span className="sf-step__icon" title={label}>
                {icon}
                <span className="visually-hidden">{label}: </span>
              </span>
              <span className="sf-step__text">{s.text}</span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
