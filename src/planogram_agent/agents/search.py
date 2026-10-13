"""Deterministic search agent wrapping product search and match decision."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..data_loader import Dataset
from ..matching import Candidate, decide_match, search_products
from ..settings import Settings, load_settings


class MatchResult(BaseModel):
    """Result of searching and matching a shopper's query item."""

    status: Literal["matched", "ambiguous", "not_found"]
    chosen: Candidate | None = None
    options: list[Candidate] = Field(default_factory=list)


def match_item(
    item_text: str,
    dataset: Dataset,
    settings: Settings | None = None,
) -> MatchResult:
    """Match shopper item text to products in dataset deterministically.

    Uses search_products and decide_match. A MatchResult must only contain
    SKUs that exist in the dataset.
    """
    if settings is None:
        settings = load_settings()

    valid_skus = {p.sku for p in dataset.products}
    candidates = search_products(item_text, top_k=settings.top_k, dataset=dataset)
    decision = decide_match(candidates, settings, dataset, query=item_text)

    if decision.status == "matched":
        if decision.candidates and decision.candidates[0].sku in valid_skus:
            return MatchResult(
                status="matched",
                chosen=decision.candidates[0],
                options=[],
            )
        return MatchResult(status="not_found", chosen=None, options=[])

    if decision.status == "ambiguous":
        valid_options = [c for c in decision.candidates if c.sku in valid_skus][:3]
        if len(valid_options) >= 2:
            return MatchResult(
                status="ambiguous",
                chosen=None,
                options=valid_options,
            )
        if len(valid_options) == 1:
            return MatchResult(
                status="matched",
                chosen=valid_options[0],
                options=[],
            )
        return MatchResult(status="not_found", chosen=None, options=[])

    return MatchResult(status="not_found", chosen=None, options=[])
