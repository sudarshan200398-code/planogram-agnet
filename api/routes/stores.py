"""Health, the store list and each store's map."""
from __future__ import annotations

from fastapi import APIRouter, Request

from .. import models
from ..deps import engine_for, engines_of

router = APIRouter()

_ZONE_TYPES = {"zone_front", "aisle", "checkout", "entrance"}


@router.get("/health", response_model=models.HealthResponse, tags=["service"])
def health(request: Request) -> models.HealthResponse:
    engines = engines_of(request)
    return models.HealthResponse(
        status="ok", stores=[models.StoreHealth(id=s, loaded=engines.is_loaded(s)) for s in engines.store_ids()]
    )


@router.get("/stores", response_model=list[models.StoreSummary], tags=["stores"])
def stores(request: Request) -> list[models.StoreSummary]:
    engines = engines_of(request)
    out = []
    for store_id in engines.store_ids():
        e = engines.get(store_id)
        out.append(models.StoreSummary(id=store_id, name=e.info.name, floors=list(e.dataset.graph.floors),
                                       product_count=len(e.dataset.products), has_prices=bool(e.prices)))
    return out


@router.get("/stores/{store_id}/map", response_model=models.MapResponse, tags=["stores"])
def store_map(store_id: str, request: Request) -> models.MapResponse:
    e = engine_for(request, store_id)
    g = e.dataset.graph
    floor_of = {n.id: n.floor for n in g.nodes}
    return models.MapResponse(
        store_id=store_id, floors=list(g.floors), bounds=models.Bounds(width=g.bounds.width, height=g.bounds.height),
        nodes=[models.MapNode(id=n.id, floor=n.floor, x=n.x, y=n.y, type=n.type.value, label=n.label) for n in g.nodes],
        edges=[models.MapEdge(a=x.a, b=x.b, floor=floor_of[x.a]) for x in g.edges],
        connectors=[models.MapConnector(a=c.a, b=c.b, type=c.type.value, accessible=c.accessible, cost=c.cost)
                    for c in g.connectors],
        zones=[models.Zone(node_id=n.id, label=n.label, floor=n.floor, type=n.type.value)
               for n in g.nodes if n.type.value in _ZONE_TYPES],
    )
