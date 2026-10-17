"""Pydantic models for every piece of data the system touches."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    ENTRANCE = "entrance"
    CHECKOUT = "checkout"
    JUNCTION = "junction"      # corridor crossing, never a destination
    ZONE_FRONT = "zone_front"  # in front of a store zone (bakery, toys, ...)
    AISLE = "aisle"            # middle of a numbered aisle
    ESCALATOR = "escalator"
    ELEVATOR = "elevator"
    STAIRS = "stairs"


class ConnectorType(str, Enum):
    ESCALATOR = "escalator"
    ELEVATOR = "elevator"
    STAIRS = "stairs"


class Node(BaseModel):
    id: str
    floor: int
    x: float
    y: float
    type: NodeType
    label: str
    # Optional other names a shopper may use for this place as a start point (e.g. "produce").
    # Checked by validators.validate_place_aliases; stores without them need nothing.
    aliases: list[str] = Field(default_factory=list)


class Edge(BaseModel):
    """Walkable link on one floor. Distance (m) defaults to straight-line."""
    a: str
    b: str
    distance: float | None = Field(default=None, gt=0)


class Connector(BaseModel):
    """Vertical link between floors. `cost` is walking-metre equivalent
    (includes waiting time for elevators)."""
    a: str
    b: str
    type: ConnectorType
    cost: float = Field(gt=0)
    accessible: bool


class Bounds(BaseModel):
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class GraphData(BaseModel):
    store_id: str
    floors: list[int]
    bounds: Bounds
    nodes: list[Node]
    edges: list[Edge]
    connectors: list[Connector]


class Product(BaseModel):
    sku: str
    name: str
    brand: str | None = None
    category: str
    size: str | None = None
    keywords: list[str] = Field(default_factory=list)


class PlanogramEntry(BaseModel):
    sku: str
    floor: int
    zone: str
    bay: str = Field(pattern=r"^[A-D]$")
    shelf_level: int = Field(ge=1, le=5)   # 1 = bottom (12"), 5 = top (72")
    position: int = Field(ge=1)
    node_id: str


class StockItem(BaseModel):
    sku: str
    quantity: int = Field(ge=0)


class Step(BaseModel):
    action: Literal["walk", "take_connector"]
    from_node: str
    to_node: str
    from_label: str
    to_label: str
    distance: float            # walking metres (0 for connectors)
    floor_from: int
    floor_to: int
    connector_type: ConnectorType | None = None


class Route(BaseModel):
    start: str
    end: str
    path: list[str]
    walking_distance: float    # metres actually walked
    total_cost: float          # walking + connector costs (what Dijkstra minimises)
    floor_changes: int
    connectors_used: list[ConnectorType]
    accessible_only: bool
    steps: list[Step]
