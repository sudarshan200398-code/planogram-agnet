"""Request and response models. Facts (stock, places, routes) come from the engine; these only shape them."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

StockStatus = Literal["in_stock", "out_of_stock", "unknown"]
ItemStatus = Literal["available", "unavailable", "not_found", "not_placed", "needs_choice", "error"]


class ErrorDetail(BaseModel):
    code: str = Field(examples=["STORE_NOT_FOUND"])
    message: str
    request_id: str


class ErrorBody(BaseModel):
    error: ErrorDetail


# ---------- stores and catalogue ----------


class StoreHealth(BaseModel):
    id: str
    loaded: bool


class HealthResponse(BaseModel):
    status: Literal["ok"]
    stores: list[StoreHealth]


class StoreSummary(BaseModel):
    id: str
    name: str
    floors: list[int]
    product_count: int
    has_prices: bool


class Category(BaseModel):
    name: str
    product_count: int


class CategoriesResponse(BaseModel):
    store_id: str
    categories: list[Category]


class Location(BaseModel):
    floor: int
    zone: str
    bay: str
    shelf: int
    node_id: str


class Product(BaseModel):
    sku: str
    name: str
    brand: str | None
    category: str
    size: str | None
    price: float | None = Field(description="Rupees; null when the store has no price for it")
    currency: Literal["INR"] = "INR"
    stock_status: StockStatus
    in_stock: int = Field(description="Units in stock")
    floor: int | None = Field(description="Primary shelf location (the route's stop for search items)")
    zone: str | None
    bay: str | None
    shelf: int | None
    locations: list[Location]
    image_url: str


class ProductPage(BaseModel):
    store_id: str
    category: str | None
    page: int
    page_size: int
    total: int
    pages: int
    items: list[Product]


class Suggestion(BaseModel):
    sku: str
    name: str
    label: str
    places: list[str]
    stock_status: StockStatus
    image_url: str


class SuggestResponse(BaseModel):
    store_id: str
    suggestions: list[Suggestion]


# ---------- search, clarify, basket ----------


class SearchRequest(BaseModel):
    text: str = Field(min_length=1, description="What the shopper typed; at most max_query_chars (500)")
    start: str | None = Field(default=None, max_length=100, description="Start point label, e.g. 'Produce'")
    step_free: bool = False


class ClarifyRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    item_index: int = Field(ge=0)
    sku: str = Field(min_length=1, max_length=64)


class BasketLine(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    qty: int = Field(description="basket_min_quantity to basket_max_quantity (1 to 99)")


class BasketRouteRequest(BaseModel):
    items: list[BasketLine] = Field(min_length=1, description="At most max_items (20) distinct skus")
    start: str | None = Field(default=None, max_length=100)
    step_free: bool = False


class SearchItem(BaseModel):
    index: int
    requested: str
    quantity_requested: int
    status: ItemStatus
    reason: str | None
    sku: str | None
    name: str | None
    brand: str | None
    category: str | None
    size: str | None
    price: float | None
    currency: Literal["INR"] = "INR"
    stock_status: StockStatus | None
    in_stock: int | None
    floor: int | None
    zone: str | None
    bay: str | None
    shelf: int | None
    locations: list[Location]
    image_url: str | None


class Option(BaseModel):
    sku: str
    name: str
    places: list[str]
    image_url: str


class QuestionOut(BaseModel):
    item_index: int
    item_text: str
    options: list[Option]


class RouteStep(BaseModel):
    number: int
    kind: Literal["walk", "take_connector", "arrive"]
    icon: str = Field(description="Material icon name: directions_walk, stairs, escalator, elevator, location_on")
    text: str
    floor: int
    to_floor: int | None


class Stop(BaseModel):
    order: int
    sku: str
    name: str
    floor: int | None
    zone: str | None
    node_id: str | None


class FloorSegments(BaseModel):
    floor: int
    lines: list[list[list[float]]] = Field(description="[[[x1, y1], [x2, y2]], ...] in map units")


class RouteOut(BaseModel):
    start_node: str
    start_label: str
    total_distance_m: float
    floor_changes: int
    accessible_only: bool
    steps: list[RouteStep]
    stops: list[Stop]
    segments: list[FloorSegments]
    path: list[str]


class SearchResponse(BaseModel):
    store_id: str
    status: str
    session_id: str | None
    verified: bool
    messages: list[str]
    items: list[SearchItem]
    question: QuestionOut | None
    route: RouteOut | None


# ---------- map ----------


class MapNode(BaseModel):
    id: str
    floor: int
    x: float
    y: float
    type: str
    label: str


class MapEdge(BaseModel):
    a: str
    b: str
    floor: int


class MapConnector(BaseModel):
    a: str
    b: str
    type: str
    accessible: bool
    cost: float


class Zone(BaseModel):
    node_id: str
    label: str
    floor: int
    type: str


class Bounds(BaseModel):
    width: float
    height: float


class MapResponse(BaseModel):
    store_id: str
    floors: list[int]
    bounds: Bounds
    nodes: list[MapNode]
    edges: list[MapEdge]
    connectors: list[MapConnector]
    zones: list[Zone]
