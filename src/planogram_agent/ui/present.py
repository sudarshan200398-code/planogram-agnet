"""Display helpers for the page: route step rows with icons, status badges and card lines.

Wording comes from the existing route and answer facts; nothing here computes a location,
distance or stock level.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from ..agents.routing import DirectionStep, format_direction_step
from ..autocomplete import suggest

if TYPE_CHECKING:
    from ..data_loader import Dataset
    from ..runtime.state import ItemResult
    from ..settings import Settings

STEP_ICONS: dict[str, str] = {
    "walk": ":material/directions_walk:",
    "stairs": ":material/stairs:",
    "escalator": ":material/escalator:",
    "elevator": ":material/elevator:",
    "arrive": ":material/location_on:",
}

_STATUS_BADGES: dict[str, tuple[str, str]] = {
    "available": ("green", "Available"),
    "unavailable": ("red", "Out of stock"),
    "needs_choice": ("orange", "Needs choice"),
    "not_found": ("gray", "Not found in catalogue"),
    "not_placed": ("gray", "Not placed on shelves"),
}


def _step_icon(step: DirectionStep) -> str:
    if step.kind == "take_connector":
        conn = getattr(step.connector_type, "value", step.connector_type)
        return STEP_ICONS.get(str(conn), STEP_ICONS["walk"])
    return STEP_ICONS[step.kind]


def step_rows(steps: Iterable[DirectionStep]) -> list[tuple[str, str]]:
    """(icon, text) per route step, in route order, worded exactly as the route directions."""
    return [(_step_icon(s), format_direction_step(s)) for s in steps]


def status_badge(status: str) -> tuple[str, str]:
    """(badge colour, text) for an item status; colour is used for status only."""
    colour, label = _STATUS_BADGES.get(status, ("gray", status.replace("_", " ").capitalize()))
    return colour, f"Status: {label}"


def search_options(term: str | None, dataset: Dataset, settings: Settings) -> list[tuple[str, tuple[str, str]]]:
    """Dropdown rows: 'Search for "<text>"' first, then matching products (label, (kind, value)).

    Kinds are "search" (run the full request on the text) and "product" (that exact sku).
    """
    text = (term or "").strip()
    if not text:
        return []
    rows = [(f'Search for "{text}"', ("search", text))]
    rows += [(s.label, ("product", s.sku)) for s in suggest(text, dataset, settings)]
    return rows


def card_lines(item: ItemResult) -> list[str]:
    """Floor and zone, bay and shelf, and 'In stock: N' for an available item."""
    loc = item.chosen_location or (item.locations[0] if item.locations else None)
    lines = (
        [f"Level {loc.floor} · {loc.zone}", f"Bay {loc.bay} · Shelf {loc.shelf_level}"]
        if loc
        else ["No shelf location"]
    )
    if item.status == "available":
        lines.append(f"In stock: {item.quantity}")
    return lines
