"""Shopping basket: plain functions over a {sku: {"name", "qty"}} dict kept in session state.

Planning a basket turns it into one exact product name per line and sends that text through the
same pipeline as typed text, on an orchestrator with no AI model, so the basket never calls one.
"""
from __future__ import annotations

import weakref
from collections.abc import MutableMapping
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from .interface import run_query
from .llm.no_model import NoModelClient
from .runtime.orchestrator import Orchestrator

if TYPE_CHECKING:
    from .runtime.state import Answer
    from .settings import Settings

Basket = MutableMapping[str, dict[str, Any]]

EMPTY_BASKET_MESSAGE = "Your basket is empty. Add products with the Add to basket buttons, then plan the route."

_BASKET_FINDERS: weakref.WeakKeyDictionary[Orchestrator, Orchestrator] = weakref.WeakKeyDictionary()


class AddResult(BaseModel):
    """Outcome of an add: refused adds leave the basket unchanged and say why."""

    ok: bool
    message: str


def clamp_quantity(qty: int, settings: Settings) -> int:
    """Keep a quantity within the configured basket limits."""
    return max(settings.basket_min_quantity, min(settings.basket_max_quantity, int(qty)))


def _line(name: str, qty: int) -> str:
    return name if qty <= 1 else f"{name} x {qty}"


def basket_text(basket: Basket) -> str:
    """One exact product name per line, with ' x N' when more than one is wanted."""
    return "\n".join(_line(entry["name"], entry["qty"]) for entry in basket.values())


def _longest_text(basket: Basket, settings: Settings) -> int:
    """Length of the basket text if every product were at the maximum quantity."""
    return len("\n".join(_line(entry["name"], settings.basket_max_quantity) for entry in basket.values()))


def add_item(basket: Basket, sku: str, name: str, settings: Settings) -> AddResult:
    """Add one of a product; a product already in the basket goes up by one, up to the maximum.

    A new product is refused if the basket would hold more than max_items products, or if its
    text could pass max_query_chars at the maximum quantity (so later edits always fit too).
    """
    if sku in basket:
        entry = basket[sku]
        if entry["qty"] >= settings.basket_max_quantity:
            return AddResult(ok=True, message=f"{name} is already at the maximum of {settings.basket_max_quantity}")
        entry["qty"] = clamp_quantity(entry["qty"] + 1, settings)
        return AddResult(ok=True, message=f"{name}: {entry['qty']} in basket")

    if len(basket) >= settings.max_items:
        return AddResult(ok=False, message=f"The basket holds at most {settings.max_items} products; {name} was not added")
    trial = {**basket, sku: {"name": name, "qty": settings.basket_min_quantity}}
    if _longest_text(trial, settings) > settings.max_query_chars:
        return AddResult(
            ok=False,
            message=f"The basket list would pass the {settings.max_query_chars}-character limit; {name} was not added",
        )
    basket[sku] = {"name": name, "qty": settings.basket_min_quantity}
    return AddResult(ok=True, message=f"{name} added to basket")


def set_quantity(basket: Basket, sku: str, qty: int, settings: Settings) -> int | None:
    """Set a product's quantity, clamped to the limits. Returns the kept quantity, or None if absent."""
    if sku not in basket:
        return None
    basket[sku]["qty"] = clamp_quantity(qty, settings)
    return basket[sku]["qty"]


def remove_item(basket: Basket, sku: str) -> None:
    basket.pop(sku, None)


def clear_basket(basket: Basket) -> None:
    basket.clear()


def basket_finder_for(finder: Orchestrator) -> Orchestrator:
    """The model-free orchestrator used for this finder's baskets, created once and kept.

    It shares the finder's dataset and settings; keeping it lets a clarification answer reach
    the orchestrator that holds the pending session.
    """
    basket_finder = _BASKET_FINDERS.get(finder)
    if basket_finder is None:
        basket_finder = Orchestrator(
            dataset=finder.dataset,
            settings=finder.settings,
            client=NoModelClient(),
            model_note="Basket: exact product names, no AI model",
        )
        _BASKET_FINDERS[finder] = basket_finder
    return basket_finder


def plan_basket(
    finder: Orchestrator,
    basket: Basket,
    *,
    start: str | None = None,
    floor: int | None = None,
    accessible_only: bool | None = None,
) -> Answer | None:
    """Send the basket through the typed-text pipeline without an AI model. None if empty."""
    if not basket:
        return None
    return run_query(
        basket_finder_for(finder),
        basket_text(basket),
        start=start,
        floor=floor,
        accessible_only=accessible_only,
    )
