"""Multi-product route planning across store floors."""
from __future__ import annotations

import itertools
import math

from pydantic import BaseModel, Field

from .data_loader import Dataset
from .graph import build_graph, shortest_path
from .schemas import ConnectorType, Route
from .settings import Settings, load_settings
from .tools import get_location


class TripPlan(BaseModel):
    ordered_skus: list[str]
    legs: list[Route]
    total_cost: float
    walking_distance: float
    floor_changes: int
    connectors_used: list[ConnectorType]
    unlocated_skus: list[str] = Field(default_factory=list)
    stops: list[tuple[str, list[str]]] = Field(default_factory=list)


def plan_route(
    dataset: Dataset,
    start_node: str,
    skus: list[str],
    accessible_only: bool = False,
    settings: Settings | None = None,
) -> TripPlan:
    """Plan a combined shortest route to retrieve multiple products.

    Starts at start_node and ends at the final stop with no return trip.
    """
    if settings is None:
        settings = load_settings()

    G = build_graph(dataset.graph)

    # 1. Lookup locations and filter out unlocated SKUs
    sku_cand_nodes: dict[str, list[str]] = {}
    unlocated_skus: list[str] = []

    for sku in skus:
        locations = get_location(sku, dataset)
        if not locations:
            unlocated_skus.append(sku)
        else:
            unique_nodes = list(dict.fromkeys(loc.node_id for loc in locations))
            sku_cand_nodes[sku] = unique_nodes

    located_skus = [s for s in skus if s in sku_cand_nodes]
    if not located_skus:
        return TripPlan(
            ordered_skus=[],
            legs=[],
            total_cost=0.0,
            walking_distance=0.0,
            floor_changes=0,
            connectors_used=[],
            unlocated_skus=unlocated_skus,
        )

    # 2. Local cache for shortest_path evaluations
    route_cache: dict[tuple[str, str], Route] = {}

    def get_leg(u: str, v: str) -> Route:
        key = (u, v)
        if key not in route_cache:
            route_cache[key] = shortest_path(G, u, v, accessible_only=accessible_only)
        return route_cache[key]

    def solve_nearest_neighbor(start: str, stops: list[str]) -> list[str]:
        curr = start
        unvisited = list(stops)
        path: list[str] = []
        while unvisited:
            nxt = min(
                unvisited,
                key=lambda s: (
                    get_leg(curr, s).total_cost,
                    get_leg(curr, s).floor_changes,
                    stops.index(s),
                ),
            )
            path.append(nxt)
            unvisited.remove(nxt)
            curr = nxt
        return path

    def eval_path(start: str, path: list[str]) -> tuple[float, int]:
        cost = 0.0
        fc = 0
        curr = start
        for nxt in path:
            leg = get_leg(curr, nxt)
            cost += leg.total_cost
            fc += leg.floor_changes
            curr = nxt
        return round(cost, 2), fc

    def solve_2opt(start: str, stops: list[str]) -> list[str]:
        order = list(stops)
        if len(order) <= 2:
            return order

        best_cost, best_fc = eval_path(start, order)
        improved = True
        while improved:
            improved = False
            for i in range(len(order)):
                for j in range(i + 1, len(order)):
                    new_order = order[:i] + order[i : j + 1][::-1] + order[j + 1 :]
                    new_cost, new_fc = eval_path(start, new_order)
                    if (new_cost < best_cost - 1e-9) or (
                        abs(new_cost - best_cost) < 1e-9 and new_fc < best_fc
                    ):
                        order = new_order
                        best_cost = new_cost
                        best_fc = new_fc
                        improved = True
                        break
                if improved:
                    break
        return order

    # 3. Estimate number of location combinations times stop orderings
    num_combos = math.prod(len(sku_cand_nodes[s]) for s in located_skus)
    all_cand_nodes = list(dict.fromkeys(
        node for nodes in sku_cand_nodes.values() for node in nodes
    ))
    max_stops = min(len(located_skus), len(all_cand_nodes))
    stop_orderings = (
        math.factorial(max_stops) if max_stops <= settings.exact_stop_limit else 1
    )
    estimated_evals = num_combos * stop_orderings

    # 4. Fallback if estimate exceeds max_plan_evaluations
    if estimated_evals > settings.max_plan_evaluations:
        curr = start_node
        unassigned = list(located_skus)
        chosen_stops: list[str] = []
        best_sku_to_node: dict[str, str] = {}

        while unassigned:
            # For products with several locations, use nearest location to previous stop (curr)
            sku_best_loc = {
                s: min(
                    sku_cand_nodes[s],
                    key=lambda node: (
                        get_leg(curr, node).total_cost,
                        get_leg(curr, node).floor_changes,
                        node,
                    ),
                )
                for s in unassigned
            }
            # Pick next stop nearest to curr
            next_sku = min(
                unassigned,
                key=lambda s: (
                    get_leg(curr, sku_best_loc[s]).total_cost,
                    get_leg(curr, sku_best_loc[s]).floor_changes,
                    skus.index(s),
                ),
            )
            next_stop = sku_best_loc[next_sku]
            chosen_stops.append(next_stop)

            # Assign all unassigned products available at next_stop
            for s in list(unassigned):
                if next_stop in sku_cand_nodes[s]:
                    best_sku_to_node[s] = next_stop
                    unassigned.remove(s)
            curr = next_stop

        unique_stops = list(dict.fromkeys(chosen_stops))
        best_order = solve_2opt(start_node, unique_stops)

    else:
        # Standard search over location combinations
        combos = itertools.product(*[sku_cand_nodes[s] for s in located_skus])
        best_key = (float("inf"), float("inf"), (), ())
        best_order: list[str] = []
        best_sku_to_node: dict[str, str] = {}

        for combo in combos:
            sku_to_node = dict(zip(located_skus, combo))
            unique_stops = list(dict.fromkeys(combo))

            if len(unique_stops) <= settings.exact_stop_limit:
                possible_orders = list(itertools.permutations(unique_stops))
            else:
                initial = solve_nearest_neighbor(start_node, unique_stops)
                possible_orders = [tuple(solve_2opt(start_node, initial))]

            for order_tuple in possible_orders:
                order = list(order_tuple)
                cost, fc = eval_path(start_node, order)

                # Determine SKU visit order for tie breaking
                cand_ordered_skus: list[str] = []
                for stop in order:
                    for s in located_skus:
                        if sku_to_node[s] == stop and s not in cand_ordered_skus:
                            cand_ordered_skus.append(s)

                sku_order_indices = tuple(skus.index(s) for s in cand_ordered_skus)
                # Deterministic key: (cost, fewer floor_changes, input order, node names)
                candidate_key = (cost, fc, sku_order_indices, tuple(order))

                if candidate_key < best_key:
                    best_key = candidate_key
                    best_order = order
                    best_sku_to_node = sku_to_node

    # 5. Build legs and compile result
    legs: list[Route] = []
    curr = start_node
    for stop in best_order:
        if stop == curr and len(best_order) > 1:
            continue
        legs.append(get_leg(curr, stop))
        curr = stop

    total_cost = round(sum(leg.total_cost for leg in legs), 2)
    walking_distance = round(sum(leg.walking_distance for leg in legs), 2)
    floor_changes = sum(leg.floor_changes for leg in legs)
    connectors_used: list[ConnectorType] = []
    for leg in legs:
        connectors_used.extend(leg.connectors_used)

    ordered_skus: list[str] = []
    stops: list[tuple[str, list[str]]] = []
    for stop in best_order:
        stop_skus: list[str] = []
        for s in located_skus:
            if best_sku_to_node[s] == stop and s not in ordered_skus:
                ordered_skus.append(s)
                stop_skus.append(s)
        if stop_skus:
            stops.append((stop, stop_skus))

    return TripPlan(
        ordered_skus=ordered_skus,
        legs=legs,
        total_cost=total_cost,
        walking_distance=walking_distance,
        floor_changes=floor_changes,
        connectors_used=connectors_used,
        unlocated_skus=unlocated_skus,
        stops=stops,
    )

