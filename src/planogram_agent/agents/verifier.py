"""Independent Verifier auditing customer-facing Answers against ground truth facts."""
from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from ..graph import build_graph, shortest_path
from ..runtime.consistency import check_directions_consistency
from ..tools import check_inventory, get_location

if TYPE_CHECKING:
    import networkx as nx
    from ..data_loader import Dataset
    from ..runtime.state import Answer, ItemResult, RunState
    from ..settings import Settings


class Problem(BaseModel):
    """Specific defect detected during answer verification."""

    code: str
    message: str
    item_index: int | None = None


class Verdict(BaseModel):
    """Result of an answer verification audit."""

    ok: bool
    problems: list[Problem] = Field(default_factory=list)


_GRAPH_CACHE: dict[int, tuple[weakref.ref[Dataset], nx.Graph]] = {}


def _get_cached_graph(dataset: Dataset) -> nx.Graph:
    """Build and cache the NetworkX graph once per dataset instance using weak references."""
    ds_id = id(dataset)
    if ds_id in _GRAPH_CACHE:
        stored_ref, g = _GRAPH_CACHE[ds_id]
        if stored_ref() is dataset:
            return g

    g = build_graph(dataset.graph)

    def _cleanup(_ref: weakref.ref, key: int = ds_id) -> None:
        _GRAPH_CACHE.pop(key, None)

    _GRAPH_CACHE[ds_id] = (weakref.ref(dataset, _cleanup), g)
    return g


def compute_expected_status(answer: Answer, state: RunState | None = None) -> str:
    """Compute the expected Answer status strictly from dataset facts and answer items.

    Independent from the composer's status logic.
    """
    if state is not None and state.parsed_request is not None:
        if state.parsed_request.intent == "unknown":
            return "error"

    if not answer.items:
        return "error"

    if answer.question is not None or any(it.status == "needs_choice" for it in answer.items):
        return "needs_clarification"

    routed_skus = set(answer.route.ordered_skus) if answer.route else set()
    all_ok = True
    for it in answer.items:
        if (
            it.status != "available"
            or it.chosen_location is None
            or it.sku not in routed_skus
        ):
            all_ok = False
            break

    if all_ok and answer.route is not None:
        return "ok"

    return "partial"


def verify_answer(
    answer: Answer,
    state: RunState,
    dataset: Dataset,
    settings: Settings,
) -> Verdict:
    """Verify answer against ground truth facts in the dataset, never trusting composer objects."""
    problems: list[Problem] = []

    prod_by_sku = {p.sku: p for p in dataset.products}
    inv_by_sku = {i.sku: i.quantity for i in dataset.inventory}
    valid_labels = {n.label for n in dataset.graph.nodes if n.label}
    connector_map = {(c.a, c.b): c for c in dataset.graph.connectors}
    for c in dataset.graph.connectors:
        connector_map[(c.b, c.a)] = c

    # 1. ITEM_NOT_ACCOUNTED check
    if state.parsed_request and state.parsed_request.items:
        req_count = len(state.parsed_request.items)
        if len(answer.items) != req_count:
            problems.append(
                Problem(
                    code="ITEM_NOT_ACCOUNTED",
                    message=f"Requested {req_count} items but answer has {len(answer.items)}",
                )
            )

    # 2. Per-item checks
    for it in answer.items:
        if it.sku is not None:
            # UNKNOWN_SKU
            if it.sku not in prod_by_sku:
                problems.append(
                    Problem(
                        code="UNKNOWN_SKU",
                        message=f"SKU '{it.sku}' does not exist in store product catalogue",
                        item_index=it.index,
                    )
                )
            else:
                p = prod_by_sku[it.sku]
                # NAME_MISMATCH
                if it.name and it.name != p.name:
                    problems.append(
                        Problem(
                            code="NAME_MISMATCH",
                            message=f"Item name '{it.name}' does not match catalog name '{p.name}'",
                            item_index=it.index,
                        )
                    )

            # STOCK_MISMATCH
            true_stock_status = check_inventory(it.sku, dataset)
            true_qty = inv_by_sku.get(it.sku, 0)
            if true_stock_status == "available":
                if it.status not in ("available", "not_placed", "needs_choice"):
                    problems.append(
                        Problem(
                            code="STOCK_MISMATCH",
                            message=f"SKU '{it.sku}' is in stock ({true_qty}) but reported as '{it.status}'",
                            item_index=it.index,
                        )
                    )
            elif true_stock_status == "unavailable":
                if it.status != "unavailable":
                    problems.append(
                        Problem(
                            code="STOCK_MISMATCH",
                            message=f"SKU '{it.sku}' is out of stock but reported as '{it.status}'",
                            item_index=it.index,
                        )
                    )
            elif true_stock_status == "unknown":
                if it.status != "not_found":
                    problems.append(
                        Problem(
                            code="STOCK_MISMATCH",
                            message=f"SKU '{it.sku}' is unknown in stock but reported as '{it.status}'",
                            item_index=it.index,
                        )
                    )

            if it.quantity != true_qty:
                problems.append(
                    Problem(
                        code="STOCK_MISMATCH",
                        message=f"SKU '{it.sku}' quantity reported as {it.quantity} but inventory is {true_qty}",
                        item_index=it.index,
                    )
                )

            # LOCATION_MISMATCH
            if it.chosen_location is not None:
                pl_match = any(
                    e.floor == it.chosen_location.floor
                    and e.zone == it.chosen_location.zone
                    and e.bay == it.chosen_location.bay
                    and e.shelf_level == it.chosen_location.shelf_level
                    and e.node_id == it.chosen_location.node_id
                    for e in dataset.planogram
                    if e.sku == it.sku
                )
                if not pl_match:
                    problems.append(
                        Problem(
                            code="LOCATION_MISMATCH",
                            message=f"Chosen location for SKU '{it.sku}' does not match any planogram row",
                            item_index=it.index,
                        )
                    )

    # 3. QUESTION_INVALID check
    if answer.question is not None:
        opts = answer.question.options
        if len(opts) < 2:
            problems.append(
                Problem(
                    code="QUESTION_INVALID",
                    message=f"Clarification question has fewer than 2 options: {len(opts)}",
                )
            )
        for opt in opts:
            if opt.sku not in prod_by_sku:
                problems.append(
                    Problem(
                        code="QUESTION_INVALID",
                        message=f"Option SKU '{opt.sku}' not in catalogue",
                    )
                )

    # 4. Route checks
    if answer.route is not None:
        route = answer.route
        G = _get_cached_graph(dataset)

        # ROUTE_ITEM_INVALID check
        available_placed = [
            it.sku
            for it in answer.items
            if it.status == "available" and it.sku and it.chosen_location is not None
        ]
        if set(route.ordered_skus) != set(available_placed):
            problems.append(
                Problem(
                    code="ROUTE_ITEM_INVALID",
                    message=f"Route SKUs {route.ordered_skus} do not match available placed SKUs {available_placed}",
                )
            )

        # ARRIVE_STEP_MISSING check
        arrive_steps = [s for s in route.steps if s.kind == "arrive"]
        arrive_skus = [s.sku for s in arrive_steps]

        for sku in route.ordered_skus:
            count = arrive_skus.count(sku)
            if count == 0:
                problems.append(
                    Problem(
                        code="ARRIVE_STEP_MISSING",
                        message=f"Missing arrive step for ordered SKU '{sku}'",
                    )
                )
            elif count > 1:
                problems.append(
                    Problem(
                        code="ARRIVE_STEP_MISSING",
                        message=f"Duplicate arrive steps for ordered SKU '{sku}' ({count})",
                    )
                )

        for s in arrive_steps:
            if s.sku in prod_by_sku:
                p = prod_by_sku[s.sku]
                if s.product_name != p.name:
                    problems.append(
                        Problem(
                            code="ARRIVE_STEP_MISSING",
                            message=f"Arrive step product name '{s.product_name}' != dataset name '{p.name}' for SKU '{s.sku}'",
                        )
                    )
                valid_loc_texts = {
                    f"Level {e.floor}, {e.zone}, Bay {e.bay}, Shelf {e.shelf_level}"
                    for e in dataset.planogram
                    if e.sku == s.sku
                }
                if not s.location_text or s.location_text not in valid_loc_texts:
                    problems.append(
                        Problem(
                            code="ARRIVE_STEP_MISSING",
                            message=f"Arrive step location_text '{s.location_text}' does not match planogram for SKU '{s.sku}'",
                        )
                    )

        # TEXT_MISMATCH check
        is_consistent, text_errs = check_directions_consistency(
            route.steps, route.directions_text
        )
        if not is_consistent:
            problems.append(
                Problem(
                    code="TEXT_MISMATCH",
                    message=f"Directions text inconsistent with steps: {'; '.join(text_errs)}",
                )
            )

        # STEP_LABEL_UNKNOWN check
        for step in route.steps:
            if step.from_label and step.from_label not in valid_labels:
                problems.append(
                    Problem(
                        code="STEP_LABEL_UNKNOWN",
                        message=f"Step from_label '{step.from_label}' not in store graph",
                    )
                )
            if step.to_label and step.to_label not in valid_labels:
                problems.append(
                    Problem(
                        code="STEP_LABEL_UNKNOWN",
                        message=f"Step to_label '{step.to_label}' not in store graph",
                    )
                )

        # CONNECTOR_NOT_ALLOWED check
        if route.accessible_only:
            accessible_types = {
                c.type.value if hasattr(c.type, "value") else str(c.type)
                for c in dataset.graph.connectors
                if c.accessible
            }
            for step in route.steps:
                if step.kind == "take_connector" and step.connector_type is not None:
                    c_type_val = (
                        step.connector_type.value
                        if hasattr(step.connector_type, "value")
                        else str(step.connector_type)
                    )
                    if c_type_val not in accessible_types:
                        problems.append(
                            Problem(
                                code="CONNECTOR_NOT_ALLOWED",
                                message=f"Step-free route uses inaccessible connector '{step.connector_type}'",
                            )
                        )
            for c_used in route.connectors_used:
                c_used_val = c_used.value if hasattr(c_used, "value") else str(c_used)
                if c_used_val not in accessible_types:
                    problems.append(
                        Problem(
                            code="CONNECTOR_NOT_ALLOWED",
                            message=f"Step-free route uses inaccessible connector '{c_used}'",
                        )
                    )

        # Leg recomputations and continuity checks
        if state.routing_result and state.routing_result.trip_plan.legs:
            legs = state.routing_result.trip_plan.legs
            # First leg starts at start_node
            if legs[0].start != route.start_node:
                problems.append(
                    Problem(
                        code="LEG_COST_MISMATCH",
                        message=f"First leg starts at '{legs[0].start}' instead of start_node '{route.start_node}'",
                    )
                )

            # Consecutive legs continuity
            for i in range(1, len(legs)):
                if legs[i].start != legs[i - 1].end:
                    problems.append(
                        Problem(
                            code="LEG_COST_MISMATCH",
                            message=f"Leg {i} starts at '{legs[i].start}', but previous leg ended at '{legs[i-1].end}'",
                        )
                    )

            # Leg end points equal chosen locations of ordered SKUs
            sku_to_loc = {
                it.sku: it.chosen_location.node_id
                for it in answer.items
                if it.sku and it.chosen_location
            }
            for sku in route.ordered_skus:
                expected_node = sku_to_loc.get(sku)
                if (
                    expected_node
                    and expected_node != route.start_node
                    and not any(leg.end == expected_node for leg in legs)
                ):
                    problems.append(
                        Problem(
                            code="ROUTE_ITEM_INVALID",
                            message=f"No route leg ends at chosen node '{expected_node}' for SKU '{sku}'",
                        )
                    )

            # Recompute leg costs with router
            for idx_leg, leg in enumerate(legs):
                calc_leg = shortest_path(
                    G, leg.start, leg.end, accessible_only=route.accessible_only
                )
                if abs(leg.total_cost - calc_leg.total_cost) > 0.01 + 1e-9:
                    problems.append(
                        Problem(
                            code="LEG_COST_MISMATCH",
                            message=f"Leg {idx_leg} cost {leg.total_cost} differs from Dijkstra {calc_leg.total_cost}",
                        )
                    )

            # TOTAL_MISMATCH check
            calc_total = round(sum(leg.total_cost for leg in legs), 2)
            if abs(route.total_cost - calc_total) > 0.01 + 1e-9:
                problems.append(
                    Problem(
                        code="TOTAL_MISMATCH",
                        message=f"Route total cost {route.total_cost} != sum of legs {calc_total}",
                    )
                )

            # FLOOR_CHANGE_MISMATCH check
            calc_fc = sum(leg.floor_changes for leg in legs)
            if route.floor_changes != calc_fc:
                problems.append(
                    Problem(
                        code="FLOOR_CHANGE_MISMATCH",
                        message=f"Route floor changes {route.floor_changes} != legs total {calc_fc}",
                    )
                )

    # 5. STATUS_INCONSISTENT check
    expected_status = compute_expected_status(answer, state)
    if answer.status != expected_status:
        problems.append(
            Problem(
                code="STATUS_INCONSISTENT",
                message=f"Answer status '{answer.status}' does not match expected '{expected_status}'",
            )
        )

    return Verdict(ok=len(problems) == 0, problems=problems)


def repair_answer(
    answer: Answer,
    verdict: Verdict,
    state: RunState,
    dataset: Dataset,
    settings: Settings,
) -> Answer:
    """Repair an invalid answer by re-deriving failing fields directly from tools."""
    prod_by_sku = {p.sku: p for p in dataset.products}
    inv_by_sku = {i.sku: i.quantity for i in dataset.inventory}

    codes = {p.code for p in verdict.problems}

    # Repair items
    repaired_items: list[ItemResult] = []
    for it in answer.items:
        it_copy = it.model_copy()
        if it_copy.sku and it_copy.sku in prod_by_sku:
            p = prod_by_sku[it_copy.sku]
            it_copy.name = p.name
            it_copy.quantity = inv_by_sku.get(it_copy.sku, 0)
            avail_status = check_inventory(it_copy.sku, dataset)
            locs = get_location(it_copy.sku, dataset)
            it_copy.locations = locs

            if avail_status == "available":
                if locs:
                    it_copy.status = "available"
                    it_copy.chosen_location = locs[0]
                else:
                    it_copy.status = "not_placed"
                    it_copy.reason = "Product has no shelf location in the planogram"
                    it_copy.chosen_location = None
            elif avail_status == "unavailable":
                it_copy.status = "unavailable"
                it_copy.reason = "Out of stock"
                it_copy.chosen_location = locs[0] if locs else None
            else:
                it_copy.status = "not_found"
                it_copy.chosen_location = None

        repaired_items.append(it_copy)

    answer.items = repaired_items

    # Repair route if needed
    if any(c in codes for c in ("ROUTE_ITEM_INVALID", "LEG_COST_MISMATCH", "TOTAL_MISMATCH", "FLOOR_CHANGE_MISMATCH", "TEXT_MISMATCH", "ARRIVE_STEP_MISSING")):
        from ..agents.routing import plan_trip
        routable = [
            it.sku for it in repaired_items
            if it.status == "available" and it.sku and it.chosen_location
        ]
        if routable and state.start_node:
            r_res = plan_trip(
                dataset,
                start_text=state.start,
                floor=state.floor,
                skus=routable,
                accessible_only=state.accessible_only,
                settings=settings,
            )
            state.routing_result = r_res
            from ..runtime.orchestrator import _build_route_summary
            answer.route = _build_route_summary(
                r_res,
                dataset,
                accessible_only=state.accessible_only,
            )
        else:
            answer.route = None

    answer.status = compute_expected_status(answer, state)
    return answer

