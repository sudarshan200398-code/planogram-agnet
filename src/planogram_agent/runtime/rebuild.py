"""Independent deterministic answer rebuild straight from dataset facts and tools."""
from __future__ import annotations

from typing import TYPE_CHECKING

from planogram_agent.agents.routing import plan_trip
from planogram_agent.agents.verifier import compute_expected_status
from planogram_agent.runtime.state import Answer, ItemResult, Question, RouteSummary
from planogram_agent.tools import check_inventory, get_location

if TYPE_CHECKING:
    from planogram_agent.data_loader import Dataset
    from planogram_agent.runtime.state import RunState
    from planogram_agent.settings import Settings
    from planogram_agent.tools import Location


def rebuild_answer(
    state: RunState,
    dataset: Dataset,
    settings: Settings,
) -> Answer:
    """Build a conservative, verified answer directly from dataset facts and tools.

    This function does NOT call or import compose_answer, enforcing architectural
    independence between the compose and rebuild pathways.
    """
    items: list[ItemResult] = []
    prod_by_sku = {p.sku: p for p in dataset.products}
    node_map = {n.id: n.label for n in dataset.graph.nodes}
    pending_idx_set = {q.item_index for q in state.pending_questions}

    if state.parsed_request and state.parsed_request.items:
        for idx, req_item in enumerate(state.parsed_request.items):
            match_res = state.matches.get(idx)

            if idx in pending_idx_set:
                items.append(
                    ItemResult(
                        index=idx,
                        requested=req_item.text,
                        qty=req_item.qty,
                        status="needs_choice",
                        sku=None,
                        name=None,
                        quantity=0,
                        locations=[],
                        chosen_location=None,
                        options=match_res.options if match_res else [],
                        reason="Item is ambiguous, needs choice",
                    )
                )
            elif match_res is None or match_res.status == "not_found":
                items.append(
                    ItemResult(
                        index=idx,
                        requested=req_item.text,
                        qty=req_item.qty,
                        status="not_found",
                        sku=None,
                        name=None,
                        quantity=0,
                        locations=[],
                        chosen_location=None,
                        options=[],
                        reason="Product not found in catalogue",
                    )
                )
            elif match_res.status == "matched" and match_res.chosen:
                sku = match_res.chosen.sku
                prod = prod_by_sku.get(sku)
                prod_name = prod.name if prod else match_res.chosen.name

                # Ground truth directly from inventory tool and dataset facts
                avail_status = check_inventory(sku, dataset)
                qty = next((inv.quantity for inv in dataset.inventory if inv.sku == sku), 0)

                # Ground truth directly from planogram location tool
                locs = get_location(sku, dataset)

                if avail_status != "available" or qty <= 0:
                    status = "unavailable"
                    reason = "Out of stock"
                    chosen_loc: Location | None = None
                elif not locs:
                    status = "not_placed"
                    reason = "Product has no shelf location in the planogram"
                    chosen_loc = None
                else:
                    status = "available"
                    reason = None
                    chosen_loc = locs[0]

                items.append(
                    ItemResult(
                        index=idx,
                        requested=req_item.text,
                        qty=req_item.qty,
                        status=status,
                        sku=sku,
                        name=prod_name,
                        quantity=qty,
                        locations=locs,
                        chosen_location=chosen_loc,
                        options=[],
                        reason=reason,
                    )
                )

    # Collect routable SKUs (available and placed)
    routable_skus: list[str] = [
        it.sku for it in items
        if it.status == "available" and it.sku and it.locations
    ]

    route_summary: RouteSummary | None = None
    if routable_skus:
        try:
            r_res = plan_trip(
                dataset,
                start_text=state.start or "Entrance",
                floor=state.floor,
                skus=routable_skus,
                accessible_only=state.accessible_only,
                settings=settings,
            )

            # Assign chosen location matching planned stop nodes
            if r_res.trip_plan.stops:
                for stop_node, stop_skus in r_res.trip_plan.stops:
                    for s in stop_skus:
                        for it in items:
                            if it.sku == s and it.locations:
                                loc_match = next((l for l in it.locations if l.node_id == stop_node), None)
                                if loc_match:
                                    it.chosen_location = loc_match

            start_label = node_map.get(r_res.start_node, r_res.start_node)
            plan = r_res.trip_plan
            route_summary = RouteSummary(
                start_node=r_res.start_node,
                start_label=start_label,
                ordered_skus=plan.ordered_skus,
                total_cost=plan.total_cost,
                walking_distance=plan.walking_distance,
                floor_changes=plan.floor_changes,
                connectors_used=plan.connectors_used,
                accessible_only=state.accessible_only,
                steps=r_res.directions,
                directions_text=r_res.directions_text,
            )
        except Exception:  # noqa: BLE001
            route_summary = None

    question: Question | None = (
        state.pending_questions[0] if state.pending_questions else None
    )

    ans = Answer(
        status="ok",
        items=items,
        route=route_summary,
        question=question,
        session_id=state.session_id,
        messages=list(state.errors),
        verified=False,
        repaired=False,
        rebuilt=True,
        trace=list(state.trace),
    )
    ans.status = compute_expected_status(ans, state)
    return ans
