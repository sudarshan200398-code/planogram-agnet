"""Search-box suggestions built on the product matcher and the store data (no AI call)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from .matching import get_search_index, normalize_text, search_products
from .tools import check_inventory, get_location

if TYPE_CHECKING:
    from .data_loader import Dataset
    from .settings import Settings

StockMarker = Literal["in_stock", "out_of_stock", "unknown"]

_STOCK_FROM_TOOL: dict[str, StockMarker] = {
    "available": "in_stock",
    "unavailable": "out_of_stock",
    "unknown": "unknown",
}
_STOCK_TEXT: dict[StockMarker, str] = {
    "in_stock": "In stock",
    "out_of_stock": "Out of stock",
    "unknown": "Stock unknown",
}


class Suggestion(BaseModel):
    """One product suggestion for the search box."""

    sku: str
    name: str
    places: list[str] = Field(default_factory=list)
    stock: StockMarker
    score: float

    @property
    def label(self) -> str:
        where = " / ".join(self.places) if self.places else "No shelf location"
        return f"{self.name} | {where} | {_STOCK_TEXT[self.stock]}"


def placement_texts(sku: str, dataset: Dataset) -> list[str]:
    """Distinct 'Level N, Zone' texts for every shelf placement of a product."""
    places: list[str] = []
    for loc in get_location(sku, dataset):
        place = f"Level {loc.floor}, {loc.zone}"
        if place not in places:
            places.append(place)
    return places


def _word_index(dataset: Dataset) -> dict[str, set[str]]:
    """Every product word from the matcher's index (single letters included) mapped to its skus."""
    words: dict[str, set[str]] = {}
    for p in get_search_index(dataset).indexed:
        for w in p.all_words:
            words.setdefault(w, set()).add(p.sku)
    return words


def _swapped_variants(word: str) -> list[str]:
    """The word with one pair of neighbouring letters swapped, e.g. 'mlik' -> 'milk'."""
    variants: list[str] = []
    for i in range(len(word) - 1):
        if word[i] != word[i + 1]:
            variants.append(word[:i] + word[i + 1] + word[i] + word[i + 2:])
    return variants


def _completions(prefix: str, words: dict[str, set[str]]) -> list[str]:
    """Index words starting with the prefix: an exact word first, then by how many products share it."""
    found = [w for w in words if w.startswith(prefix)]
    return sorted(found, key=lambda w: (w != prefix, -len(words[w]), w))


def _make(sku: str, name: str, score: float, dataset: Dataset) -> Suggestion:
    return Suggestion(
        sku=sku,
        name=name,
        places=placement_texts(sku, dataset),
        stock=_STOCK_FROM_TOOL[check_inventory(sku, dataset)],
        score=score,
    )


def suggest(text: str, dataset: Dataset, settings: Settings) -> list[Suggestion]:
    """Suggest products for what the shopper has typed so far, best first, capped by config.

    The last typed word is treated as a prefix and completed against the matcher's word index;
    earlier words must appear in the product. Completions shared by more products come first.
    If nothing completes, one swapped pair of letters is tried, then the matcher's own search.
    """
    norm = normalize_text(text or "")
    if len(norm.replace(" ", "")) < settings.autocomplete_min_chars:
        return []

    limit = settings.autocomplete_limit
    words = _word_index(dataset)
    head, last = norm.split()[:-1], norm.split()[-1]
    names = {p.sku: p.name for p in dataset.products}

    allowed = set(names)
    for w in head:
        allowed &= words.get(w, set())

    completions = _completions(last, words)
    if not completions and len(last) >= 3:
        for variant in _swapped_variants(last):
            completions += [c for c in _completions(variant, words) if c not in completions]

    results: list[Suggestion] = []
    seen: set[str] = set()
    for word in completions:
        group = (words[word] & allowed) - seen
        if not group:
            continue
        scores = {
            c.sku: c.score
            for c in search_products(" ".join([*head, word]), len(names), dataset)
        }
        for sku in sorted(group, key=lambda s: (-scores.get(s, 0.0), names[s])):
            results.append(_make(sku, names[sku], scores.get(sku, 0.0), dataset))
            seen.add(sku)
            if len(results) >= limit:
                return results

    if results:
        return results

    return [
        _make(c.sku, c.name, c.score, dataset)
        for c in search_products(norm, limit, dataset)
        if c.score >= settings.ask_threshold
    ]
