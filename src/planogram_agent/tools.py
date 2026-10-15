"""Deterministic lookup tools holding store facts."""
from __future__ import annotations

from pydantic import BaseModel

from .data_loader import Dataset
from .matching import (
    Candidate,
    MatchDecision,
    decide_match,
    normalize_text,
    search_products,
)
from .schemas import NodeType


class Location(BaseModel):
    floor: int
    zone: str
    bay: str
    shelf_level: int
    node_id: str


def check_inventory(sku: str, dataset: Dataset) -> str:
    """Check stock level for a SKU.

    Returns:
        'available' if quantity > 0,
        'unavailable' if quantity == 0,
        'unknown' if the sku is not in the stock data.
    """
    for item in dataset.inventory:
        if item.sku == sku:
            return "available" if item.quantity > 0 else "unavailable"
    return "unknown"


def get_location(sku: str, dataset: Dataset) -> list[Location]:
    """Get product placements from the planogram.

    Returns:
        List of Location objects, or empty list if the product is not placed.
    """
    locations: list[Location] = []
    for entry in dataset.planogram:
        if entry.sku == sku:
            locations.append(Location(
                floor=entry.floor,
                zone=entry.zone,
                bay=entry.bay,
                shelf_level=entry.shelf_level,
                node_id=entry.node_id,
            ))
    return locations


def _normalize_label(text: str) -> str:
    """Normalize label for start point comparison, stripping leading 'the '."""
    if not text:
        return ""
    t = normalize_text(text)
    if t.startswith("the "):
        t = t[4:].strip()
    return t


def resolve_start(text: str | None, dataset: Dataset, floor: int | None = None) -> str:
    """Map a landmark name like 'bakery' or 'the Bakery' to a map point node ID.

    If text is empty or None, returns the entrance node id.
    Labels that exist on both floors (Escalators, Elevator, Stairs) require a floor argument;
    if not provided, raises a ValueError listing the options.
    If nothing matches, raises a ValueError listing valid landmark names.
    """
    if text is None or not str(text).strip():
        for node in dataset.graph.nodes:
            if node.type == NodeType.ENTRANCE:
                return node.id
        raise ValueError("No entrance node defined in store graph")

    norm_target = _normalize_label(str(text))
    matching_nodes = [
        node for node in dataset.graph.nodes
        if _normalize_label(node.label) == norm_target
    ]

    if not matching_nodes:
        valid_labels = sorted({
            n.label for n in dataset.graph.nodes
            if n.type != NodeType.JUNCTION
        })
        raise ValueError(
            f"Unknown start point '{text}'. Valid names: {', '.join(valid_labels)}"
        )

    distinct_floors = {n.floor for n in matching_nodes}
    if len(distinct_floors) > 1:
        if floor is not None:
            for n in matching_nodes:
                if n.floor == floor:
                    return n.id
            raise ValueError(
                f"Start point '{text}' not found on Level {floor}."
            )
        options = [
            f"{n.label} (Level {n.floor})"
            for n in sorted(matching_nodes, key=lambda x: x.floor)
        ]
        raise ValueError(
            f"Start point '{text}' exists on multiple floors. Please specify a floor: {', '.join(options)}"
        )

    if floor is not None and matching_nodes[0].floor != floor:
        raise ValueError(
            f"Start point '{text}' not found on Level {floor}."
        )

    return matching_nodes[0].id


__all__ = [
    "Candidate",
    "Location",
    "MatchDecision",
    "check_inventory",
    "decide_match",
    "get_location",
    "normalize_text",
    "resolve_start",
    "search_products",
]
