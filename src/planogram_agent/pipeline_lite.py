"""Temporary pipeline helper chaining Query, Search, Availability, and Routing agents.

NOTE: This module is temporary and will be replaced by the Orchestrator in Phase 7.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .agents.availability import check_availability
from .agents.query import rule_based_fallback
from .agents.routing import RoutingResult, plan_trip
from .agents.search import match_item
from .data_loader import Dataset
from .matching import Candidate
from .settings import Settings, load_settings
from .tools import get_location


class PipelineItemResult(BaseModel):
    """Result for an individual query item through the pipeline."""

    text: str
    status: Literal["matched", "ambiguous", "not_found"]
    chosen_sku: str | None = None
    options: list[Candidate] = Field(default_factory=list)
    availability: Literal["available", "unavailable", "unknown"] | None = None
    quantity: int = 0
    locations: list[dict] = Field(default_factory=list)


class PipelineResult(BaseModel):
    """Combined end-to-end result across query interpretation, search, stock, and route."""

    response_status: Literal["ok", "partial", "needs_clarification", "error"]
    items: list[PipelineItemResult] = Field(default_factory=list)
    routing: RoutingResult | None = None


def run_pipeline_lite(
    query: str,
    dataset: Dataset,
    settings: Settings | None = None,
    start: str | None = None,
    floor: int | None = None,
    accessible_only: bool | None = None,
) -> PipelineResult:
    """Run shopper query end-to-end through deterministic agents without AI models.

    Uses the start point, floor, and step-free flag found by the Query agent
    unless the caller passes explicit values.
    """
    if settings is None:
        settings = load_settings()

    # 1. Query agent (rule-based fallback, no AI model)
    parsed = rule_based_fallback(query, settings, dataset=dataset)
    if parsed.intent == "unknown" or not parsed.items:
        return PipelineResult(
            response_status="error",
            items=[],
            routing=None,
        )

    # Use Query agent values unless caller passes explicit overrides
    resolved_start = start if start is not None else parsed.start
    resolved_floor = floor if floor is not None else None
    resolved_accessible = (
        accessible_only if accessible_only is not None else parsed.accessible_only
    )

    # 2. Search & 3. Availability agents
    item_results: list[PipelineItemResult] = []
    has_ambiguous = False
    has_unfulfilled = False
    routable_skus: list[str] = []

    for it in parsed.items:
        match_res = match_item(it.text, dataset, settings)

        if match_res.status == "matched" and match_res.chosen:
            sku = match_res.chosen.sku
            avail = check_availability(sku, dataset)
            locs = get_location(sku, dataset)
            loc_dicts = [loc.model_dump() for loc in locs]

            item_results.append(
                PipelineItemResult(
                    text=it.text,
                    status="matched",
                    chosen_sku=sku,
                    options=[],
                    availability=avail.status,
                    quantity=avail.quantity,
                    locations=loc_dicts,
                )
            )

            if avail.status == "available":
                routable_skus.append(sku)
            else:
                has_unfulfilled = True

        elif match_res.status == "ambiguous":
            has_ambiguous = True
            item_results.append(
                PipelineItemResult(
                    text=it.text,
                    status="ambiguous",
                    chosen_sku=None,
                    options=match_res.options,
                    availability=None,
                    quantity=0,
                    locations=[],
                )
            )

        else:
            has_unfulfilled = True
            item_results.append(
                PipelineItemResult(
                    text=it.text,
                    status="not_found",
                    chosen_sku=None,
                    options=[],
                    availability=None,
                    quantity=0,
                    locations=[],
                )
            )

    # 4. Routing agent & Response status arbitration
    if has_ambiguous:
        resp_status = "needs_clarification"
        routing_res = None
    elif has_unfulfilled:
        resp_status = "partial"
        if routable_skus:
            routing_res = plan_trip(
                dataset,
                start_text=resolved_start,
                floor=resolved_floor,
                skus=routable_skus,
                accessible_only=resolved_accessible,
                settings=settings,
            )
        else:
            routing_res = None
    else:
        resp_status = "ok"
        routing_res = plan_trip(
            dataset,
            start_text=resolved_start,
            floor=resolved_floor,
            skus=routable_skus,
            accessible_only=resolved_accessible,
            settings=settings,
        )

    return PipelineResult(
        response_status=resp_status,
        items=item_results,
        routing=routing_res,
    )
