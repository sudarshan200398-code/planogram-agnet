"""Deterministic routing agent producing structured trip plans and directions."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..data_loader import Dataset
from ..planner import TripPlan, plan_route
from ..schemas import ConnectorType
from ..settings import Settings, load_settings
from ..tools import get_location, resolve_start


class DirectionStep(BaseModel):
    """A single structured step in the shopper navigation itinerary."""

    kind: Literal["walk", "take_connector", "arrive"]
    floor: int
    to_floor: int | None = None
    from_label: str = ""
    to_label: str = ""
    distance: float = 0.0
    connector_type: ConnectorType | None = None
    sku: str | None = None
    location_text: str | None = None
    product_name: str | None = None


class RoutingResult(BaseModel):
    """Routing result containing the TripPlan and human-readable directions."""

    trip_plan: TripPlan
    start_node: str
    directions: list[DirectionStep] = Field(default_factory=list)
    directions_text: str = ""

    @property
    def unlocated_skus(self) -> list[str]:
        """Read unlocated products directly from the trip plan without duplication."""
        return self.trip_plan.unlocated_skus


def format_direction_step(step: DirectionStep) -> str:
    """Format a structured DirectionStep into a plain-English line (no AI)."""
    if step.kind == "walk":
        dist_m = round(step.distance)
        if dist_m == 0:
            return f"Walk less than 1 m from {step.from_label} to {step.to_label}."
        return f"Walk {dist_m}m from {step.from_label} to {step.to_label}."

    if step.kind == "take_connector":
        conn = (
            step.connector_type.value
            if hasattr(step.connector_type, "value")
            else str(step.connector_type)
        )
        return f"Take the {conn} from Level {step.floor} to Level {step.to_floor}."

    if step.kind == "arrive":
        name = step.product_name or step.sku or ""
        loc_part = f" ({step.location_text})" if step.location_text else ""
        return f"Arrive at {step.to_label} for {name}{loc_part}."

    return ""


def format_directions(steps: list[DirectionStep]) -> str:
    """Produce plain-English text from structured direction steps with a template function."""
    lines: list[str] = []
    for idx, step in enumerate(steps, 1):
        line = format_direction_step(step)
        if line:
            lines.append(f"{idx}. {line}")
    return "\n".join(lines)


def build_direction_steps(
    trip_plan: TripPlan,
    dataset: Dataset,
    start_node: str,
) -> list[DirectionStep]:
    """Build structured directions as data from a TripPlan.

    The arrive step uses the planogram entry whose map point is the stop the
    planner chose for that product, never the first row. If several products share
    a stop, one arrive step is produced for each.
    """
    steps: list[DirectionStep] = []
    node_map = {n.id: n for n in dataset.graph.nodes}
    prod_map = {p.sku: p.name for p in dataset.products}

    def _emit_arrive_steps_for_skus(stop_node_id: str, skus: list[str]) -> None:
        stop_node_obj = node_map.get(stop_node_id)
        dest_label = stop_node_obj.label if stop_node_obj else stop_node_id
        for sku in skus:
            matching_entry = next(
                (
                    e
                    for e in dataset.planogram
                    if e.sku == sku and e.node_id == stop_node_id
                ),
                None,
            )
            if matching_entry is None:
                matching_entry = next(
                    (e for e in dataset.planogram if e.sku == sku),
                    None,
                )
            loc_text = (
                f"Level {matching_entry.floor}, {matching_entry.zone}, "
                f"Bay {matching_entry.bay}, Shelf {matching_entry.shelf_level}"
            ) if matching_entry else ""
            floor_val = matching_entry.floor if matching_entry else (stop_node_obj.floor if stop_node_obj else 1)
            steps.append(
                DirectionStep(
                    kind="arrive",
                    floor=floor_val,
                    from_label=dest_label,
                    to_label=dest_label,
                    distance=0.0,
                    sku=sku,
                    product_name=prod_map.get(sku, sku),
                    location_text=loc_text,
                )
            )

    if trip_plan.stops:
        stops_to_process = list(trip_plan.stops)
        # 1. Arrive steps for products located at start_node come first, before any walking
        if stops_to_process and stops_to_process[0][0] == start_node:
            first_node, first_skus = stops_to_process.pop(0)
            _emit_arrive_steps_for_skus(first_node, first_skus)

        # 2. Each leg is its walk and connector steps followed by arrive steps for that leg's end stop
        for leg, (stop_node_id, stop_skus) in zip(trip_plan.legs, stops_to_process):
            for route_step in leg.steps:
                if route_step.action == "walk":
                    steps.append(
                        DirectionStep(
                            kind="walk",
                            floor=route_step.floor_from,
                            from_label=route_step.from_label,
                            to_label=route_step.to_label,
                            distance=route_step.distance,
                        )
                    )
                elif route_step.action == "take_connector":
                    steps.append(
                        DirectionStep(
                            kind="take_connector",
                            floor=route_step.floor_from,
                            to_floor=route_step.floor_to,
                            from_label=route_step.from_label,
                            to_label=route_step.to_label,
                            distance=0.0,
                            connector_type=route_step.connector_type,
                        )
                    )
            _emit_arrive_steps_for_skus(stop_node_id, stop_skus)

        return steps

    # Legacy fallback if trip_plan.stops is empty
    remaining_skus = list(trip_plan.ordered_skus)

    def _emit_arrive_steps_for_stop(stop_node_id: str) -> None:
        stop_node_obj = node_map.get(stop_node_id)
        dest_label = stop_node_obj.label if stop_node_obj else stop_node_id

        while remaining_skus:
            cand_sku = remaining_skus[0]
            matching_entry = next(
                (
                    e
                    for e in dataset.planogram
                    if e.sku == cand_sku and e.node_id == stop_node_id
                ),
                None,
            )
            if matching_entry is None:
                break

            remaining_skus.pop(0)
            loc_text = (
                f"Level {matching_entry.floor}, {matching_entry.zone}, "
                f"Bay {matching_entry.bay}, Shelf {matching_entry.shelf_level}"
            )
            steps.append(
                DirectionStep(
                    kind="arrive",
                    floor=matching_entry.floor,
                    from_label=dest_label,
                    to_label=dest_label,
                    distance=0.0,
                    sku=cand_sku,
                    product_name=prod_map.get(cand_sku, cand_sku),
                    location_text=loc_text,
                )
            )

    if not trip_plan.legs:
        _emit_arrive_steps_for_stop(start_node)
        return steps

    for leg in trip_plan.legs:
        for route_step in leg.steps:
            if route_step.action == "walk":
                steps.append(
                    DirectionStep(
                        kind="walk",
                        floor=route_step.floor_from,
                        from_label=route_step.from_label,
                        to_label=route_step.to_label,
                        distance=route_step.distance,
                    )
                )
            elif route_step.action == "take_connector":
                steps.append(
                    DirectionStep(
                        kind="take_connector",
                        floor=route_step.floor_from,
                        to_floor=route_step.floor_to,
                        from_label=route_step.from_label,
                        to_label=route_step.to_label,
                        distance=0.0,
                        connector_type=route_step.connector_type,
                    )
                )

        _emit_arrive_steps_for_stop(leg.end)

    return steps


def plan_trip(
    dataset: Dataset,
    start_text: str | None = None,
    floor: int | None = None,
    skus: list[str] | None = None,
    accessible_only: bool = False,
    settings: Settings | None = None,
) -> RoutingResult:
    """Plan trip route and produce structured directions and directions_text."""
    if settings is None:
        settings = load_settings()

    sku_list = list(skus or [])
    start_node = resolve_start(start_text, dataset, floor=floor)

    trip_plan = plan_route(
        dataset,
        start_node=start_node,
        skus=sku_list,
        accessible_only=accessible_only,
        settings=settings,
    )

    direction_steps = build_direction_steps(trip_plan, dataset, start_node)
    text = format_directions(direction_steps)

    return RoutingResult(
        trip_plan=trip_plan,
        start_node=start_node,
        directions=direction_steps,
        directions_text=text,
    )
