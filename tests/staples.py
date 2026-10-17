"""Everyday staples a supermarket should sell, and how to tell a search really found one.

Shared by tests/test_staples.py (Riverside must find all of them) and scripts/audit_staples.py (report).
"""
from __future__ import annotations

from planogram_agent.data_loader import Dataset
from planogram_agent.matching import decide_match, search_products
from planogram_agent.settings import Settings

# (what a shopper types, words of which at least one must be in a found product's name)
STAPLES: list[tuple[str, tuple[str, ...]]] = [
    ("milk", ("milk",)),
    ("full cream milk", ("full cream",)),
    ("toned milk", ("toned",)),
    ("skimmed milk", ("skimmed",)),
    ("curd", ("curd",)),
    ("yogurt", ("yogurt", "yoghurt")),
    ("eggs", ("egg",)),
    ("bread", ("bread",)),
    ("butter", ("butter",)),
    ("cheese", ("cheese",)),
    ("paneer", ("paneer",)),
    ("rice", ("rice",)),
    ("atta", ("atta",)),
    ("wheat flour", ("wheat",)),
    ("sugar", ("sugar",)),
    ("salt", ("salt",)),
    ("cooking oil", ("oil",)),
    ("tea", ("tea",)),
    ("coffee", ("coffee",)),
    ("biscuits", ("biscuit", "cookie")),
    ("instant noodles", ("noodle",)),
    ("onions", ("onion",)),
    ("potatoes", ("potato",)),
    ("tomatoes", ("tomato",)),
    ("bananas", ("banana",)),
    ("apples", ("apple",)),
    ("bottled water", ("water",)),
    ("soft drinks", ("soft drink",)),
    ("juice", ("juice",)),
    ("chips", ("chip",)),
    ("chocolate", ("chocolate",)),
    ("detergent", ("detergent",)),
    ("soap", ("soap",)),
    ("shampoo", ("shampoo",)),
    ("toothpaste", ("toothpaste",)),
    ("tissue", ("tissue",)),
    ("toilet paper", ("toilet",)),
    ("dish wash", ("dish",)),
    ("garbage bags", ("garbage",)),
    ("batteries", ("batter",)),
    ("notebooks", ("notebook",)),
    ("pens", ("pen",)),
]


def find_staple(query: str, expected: tuple[str, ...], dataset: Dataset, settings: Settings) -> tuple[str, list[str]]:
    """The real search decision for `query`, and the names it offers that really are the staple."""
    candidates = search_products(query, top_k=settings.top_k, dataset=dataset)
    decision = decide_match(candidates, settings, dataset, query)
    names = [c.name for c in decision.candidates]
    hits = [n for n in names if any(e in n.lower() for e in expected)]
    return decision.status, hits


def missing_staples(dataset: Dataset, settings: Settings) -> list[str]:
    missing = []
    for query, expected in STAPLES:
        status, hits = find_staple(query, expected, dataset, settings)
        if status == "not_found" or not hits:
            missing.append(query)
    return missing
