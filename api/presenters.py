"""Turn engine results into API responses. Every fact comes from the store's own dataset or answer."""
from __future__ import annotations

import math

from planogram_agent.agents.routing import DirectionStep
from planogram_agent.autocomplete import Suggestion as EngineSuggestion
from planogram_agent.autocomplete import placement_texts
from planogram_agent.runtime.state import Answer, ItemResult
from planogram_agent.tools import Location as EngineLocation
from planogram_agent.tools import get_location
from planogram_agent.ui.map_plot import route_floor_segments
from planogram_agent.ui.present import step_rows

from . import models
from .engines import StoreEngine

_STOCK = {"in_stock": "in_stock", "out_of_stock": "out_of_stock", "unknown": "unknown"}


def image_url(store_id: str, sku: str) -> str:
    return f"/stores/{store_id}/products/{sku}/image"


def _location(loc: EngineLocation) -> models.Location:
    return models.Location(floor=loc.floor, zone=loc.zone, bay=loc.bay, shelf=loc.shelf_level, node_id=loc.node_id)


def _stock(engine: StoreEngine, sku: str) -> tuple[str, int]:
    qty = engine.inventory.get(sku)
    if qty is None:
        return "unknown", 0
    return ("in_stock" if qty > 0 else "out_of_stock"), qty


def product_fields(engine: StoreEngine, sku: str, primary: EngineLocation | None = None) -> dict:
    """Shared product fields for browse results, product detail and search items."""
    p = engine.product(sku)
    locs = get_location(sku, engine.dataset)
    first = primary or (locs[0] if locs else None)
    stock_status, qty = _stock(engine, sku)
    return {
        "sku": p.sku, "name": p.name, "brand": p.brand, "category": p.category, "size": p.size,
        "price": engine.prices.get(sku), "currency": "INR", "stock_status": stock_status, "in_stock": qty,
        "floor": first.floor if first else None, "zone": first.zone if first else None,
        "bay": first.bay if first else None, "shelf": first.shelf_level if first else None,
        "locations": [_location(l) for l in locs], "image_url": image_url(engine.info.id, sku),
    }


def product(engine: StoreEngine, sku: str) -> models.Product:
    return models.Product(**product_fields(engine, sku))


def suggestion(engine: StoreEngine, s: EngineSuggestion) -> models.Suggestion:
    return models.Suggestion(sku=s.sku, name=s.name, label=s.label, places=s.places,
                             stock_status=_STOCK[s.stock], image_url=image_url(engine.info.id, s.sku))


_EMPTY_PRODUCT = {k: None for k in ("sku", "name", "brand", "category", "size", "price", "stock_status", "in_stock",
                                    "floor", "zone", "bay", "shelf", "image_url")}


def _item(engine: StoreEngine, it: ItemResult) -> models.SearchItem:
    fields = product_fields(engine, it.sku, it.chosen_location) if it.sku else {**_EMPTY_PRODUCT, "locations": []}
    return models.SearchItem(index=it.index, requested=it.requested, quantity_requested=it.qty,
                             status=it.status, reason=it.reason, **fields)


def _steps(steps: list[DirectionStep]) -> list[models.RouteStep]:
    out = []
    for number, (step, (icon, text)) in enumerate(zip(steps, step_rows(steps)), start=1):
        out.append(models.RouteStep(number=number, kind=step.kind, icon=icon.removeprefix(":material/").rstrip(":"),
                                    text=text, floor=step.floor, to_floor=step.to_floor))
    return out


def _route(engine: StoreEngine, answer: Answer) -> models.RouteOut | None:
    route = answer.route
    if route is None:
        return None
    nodes = {n.id: n for n in engine.dataset.graph.nodes}
    chosen = {it.sku: it.chosen_location for it in answer.items if it.sku}
    stops = []
    for order, sku in enumerate(route.ordered_skus, start=1):
        loc = chosen.get(sku)
        stops.append(models.Stop(order=order, sku=sku, name=engine.product(sku).name,
                                 floor=loc.floor if loc else None, zone=loc.zone if loc else None,
                                 node_id=loc.node_id if loc else None))
    segments = [
        models.FloorSegments(floor=floor, lines=[[[nodes[u].x, nodes[u].y], [nodes[v].x, nodes[v].y]] for u, v in pairs])
        for floor, pairs in sorted(route_floor_segments(engine.dataset, answer).items())
    ]
    return models.RouteOut(
        start_node=route.start_node, start_label=route.start_label,
        total_distance_m=round(route.walking_distance, 1), floor_changes=route.floor_changes,
        accessible_only=route.accessible_only, steps=_steps(route.steps), stops=stops, segments=segments,
        path=list(route.path),
    )


def _question(engine: StoreEngine, answer: Answer) -> models.QuestionOut | None:
    q = answer.question
    if q is None:
        return None
    options = [models.Option(sku=o.sku, name=o.name, places=placement_texts(o.sku, engine.dataset),
                             image_url=image_url(engine.info.id, o.sku)) for o in q.options]
    return models.QuestionOut(item_index=q.item_index, item_text=q.item_text, options=options)


def search_response(engine: StoreEngine, answer: Answer) -> models.SearchResponse:
    return models.SearchResponse(
        store_id=engine.info.id, status=answer.status, session_id=answer.session_id, verified=answer.verified,
        messages=list(answer.messages), items=[_item(engine, it) for it in answer.items],
        question=_question(engine, answer), route=_route(engine, answer),
    )


def page_count(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / page_size))
