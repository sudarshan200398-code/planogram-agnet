"""Everyday staples are findable in Riverside Market, and adding them changed none of its existing products."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
from collections import deque
from pathlib import Path

import pytest

from planogram_agent.data_loader import load_dataset
from planogram_agent.schemas import NodeType
from planogram_agent.settings import load_settings
from tests.staples import STAPLES, find_staple

ROOT = Path(__file__).resolve().parent.parent
RIVERSIDE = ROOT / "data" / "store_riverside"

# The 444 Riverside products that existed before the staples were added: their product, placement,
# stock and price rows (sorted, joined) must never change. Recorded from the committed files.
ORIGINAL_COUNT = 444
ORIGINAL_HASHES = {
    "products.csv": "4aac47723e0ccc3963a1a0f477ae2ffb2991f0295c3732ba3fc238f9243995e4",
    "planogram.csv": "14c3f4555d6ce1b3882dff2be0e6653d3af6cffb09410045d14b481fed0d1d97",
    "inventory.csv": "9b6139a4c60911cd1ff4dce4b3be706155ea6b033601df03164c9f6e785e7fb7",
    "prices.csv": "11474683dfa0cac58f8677320cd8ae3878ae0ef9f09d8b1a618565d839fc844c",
}


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows(name: str) -> list[dict]:
    with open(RIVERSIDE / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def riverside():
    return load_dataset(RIVERSIDE, validate=True)


@pytest.fixture(scope="module")
def staple_skus() -> set[str]:
    gen = _script("generate_store_riverside")
    return {p["sku"] for p in gen.build_products() if p["sku"].split("-")[1] in gen.STAPLE_CODES}


@pytest.mark.parametrize("query, expected", STAPLES, ids=[q for q, _ in STAPLES])
def test_riverside_finds_every_staple_by_name(riverside, query, expected):
    status, hits = find_staple(query, expected, riverside, load_settings())
    assert status != "not_found" and hits, f"{query!r}: {status}, no product named {expected}"


def test_existing_riverside_products_unchanged(staple_skus):
    original = {r["sku"] for r in _rows("products.csv")} - staple_skus
    assert len(original) == ORIGINAL_COUNT
    for name, expected in ORIGINAL_HASHES.items():
        lines = sorted("|".join(r.values()) for r in _rows(name) if r["sku"] in original)
        assert hashlib.sha256("\n".join(lines).encode()).hexdigest() == expected, name


def test_new_staples_are_placed_reachable_and_some_out_of_stock(riverside, staple_skus):
    graph = riverside.graph
    neighbours: dict[str, set[str]] = {n.id: set() for n in graph.nodes}
    for e in [*graph.edges, *graph.connectors]:
        neighbours[e.a].add(e.b)
        neighbours[e.b].add(e.a)
    entrance = next(n.id for n in graph.nodes if n.type == NodeType.ENTRANCE)
    reached, queue = {entrance}, deque([entrance])
    while queue:
        for nxt in neighbours[queue.popleft()] - reached:
            reached.add(nxt)
            queue.append(nxt)

    placed = {e.sku: e for e in riverside.planogram if e.sku in staple_skus}
    assert set(placed) == staple_skus
    assert all(e.node_id in reached for e in placed.values())
    stock = {s.sku: s.quantity for s in riverside.inventory if s.sku in staple_skus}
    assert 2 <= sum(q == 0 for q in stock.values()) < len(stock) // 4


def test_new_staples_are_priced_by_a_product_rule(staple_skus):
    pricing = _script("generate_store_prices")
    results = [r for r in pricing.price_store(RIVERSIDE, pricing.load_rules()) if r.sku in staple_skus]
    assert {r.sku for r in results} == staple_skus
    assert [r.name for r in results if r.source != "rule"] == []
