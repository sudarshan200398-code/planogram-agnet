"""Start phrases at the end of a list, place aliases (optional, per store), and the "then" connector."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from planogram_agent.agents.query import rule_based_fallback
from planogram_agent.providers import LocalFilesProvider
from planogram_agent.settings import load_settings
from planogram_agent.tools import resolve_start
from planogram_agent import validators

SETTINGS = load_settings()


@pytest.fixture(scope="module")
def stores():
    p = LocalFilesProvider()
    return {s: p.load_dataset(s) for s in ("central", "riverside")}


def parse(stores, store: str, text: str):
    r = rule_based_fallback(text, SETTINGS, stores[store])
    return r.start, [i.text for i in r.items]


# ---------- trailing start clauses ----------

# (store, text, expected start label, expected items). Fillers have the usual typos (im, i'm, i am).
TRAILING = [
    # Riverside: "produce", "dairy" and "bakery" are aliases of its own places
    ("riverside", "milk, eggs, brd and im at produce", "Fresh Market", ["milk", "eggs", "brd"]),
    ("riverside", "milk, eggs, brd, im at produce", "Fresh Market", ["milk", "eggs", "brd"]),
    ("riverside", "milk and eggs and i'm at produce", "Fresh Market", ["milk", "eggs"]),
    ("riverside", "milk, eggs and i am near bakery", "Bakehouse", ["milk", "eggs"]),
    ("riverside", "milk, eggs starting from produce", "Fresh Market", ["milk", "eggs"]),
    ("riverside", "milk and eggs, I'm in the dairy section", "Chilled Foods", ["milk", "eggs"]),
    ("riverside", "milk, eggs, im near the produce section", "Fresh Market", ["milk", "eggs"]),
    ("riverside", "milk, eggs then im at produce", "Fresh Market", ["milk", "eggs"]),
    ("riverside", "milk, eggs then im near fresh market", "Fresh Market", ["milk", "eggs"]),
    # Central: its own place names (no aliases)
    ("central", "milk, eggs, brd and im at produce", "Produce", ["milk", "eggs", "brd"]),
    ("central", "milk and eggs and i am near bakery", "Bakery", ["milk", "eggs"]),
    ("central", "milk, eggs starting from produce", "Produce", ["milk", "eggs"]),
    ("central", "milk, eggs then im at produce", "Produce", ["milk", "eggs"]),
    ("central", "milk then eggs then i'm near the bakery", "Bakery", ["milk", "eggs"]),
]


@pytest.mark.parametrize("store,text,start,items", TRAILING, ids=[f"{s}: {t}" for s, t, *_ in TRAILING])
def test_trailing_start_clause(stores, store, text, start, items):
    assert parse(stores, store, text) == (start, items)


def test_then_splits_items_like_and(stores):
    for store in ("central", "riverside"):
        assert parse(stores, store, "milk then eggs then bread") == (None, ["milk", "eggs", "bread"])


def test_a_start_in_the_middle_of_a_list_keeps_working(stores):
    # Not new: a start clause between items was already recognised; it still is, with aliases too.
    assert parse(stores, "central", "milk, im at produce, eggs") == ("Produce", ["milk", "eggs"])
    assert parse(stores, "riverside", "milk, im at produce, eggs") == ("Fresh Market", ["milk", "eggs"])


# ---------- what must stay a product or an item ----------

@pytest.mark.parametrize("store", ["central", "riverside"])
@pytest.mark.parametrize("text,items", [
    ("milk, eggs and im at narnia", ["milk", "eggs", "im at narnia"]),  # unknown place stays an item
    ("bread at home", ["bread at home"]),
    ("milk near me", ["milk near me"]),
])
def test_unknown_places_and_lookalikes_stay_items(stores, store, text, items):
    assert parse(stores, store, text) == (None, items)


def test_store_1_has_no_aliases_so_its_unknown_names_stay_items(stores):
    # Central's place is "Dairy & Frozen"; it has no aliases, so "dairy" is not a start there.
    assert parse(stores, "central", "milk and eggs, I'm in the dairy section") == (
        None, ["milk", "eggs", "I'm in the dairy section"])
    assert all(not n.aliases for n in stores["central"].graph.nodes)


@pytest.mark.parametrize("text", ["cat food", "dairy milk", "produce", "fresh market vegetables"])
def test_product_words_and_bare_aliases_are_not_starts(stores, text):
    start, items = parse(stores, "riverside", text)
    assert start is None and items == [text]


# ---------- alias resolution and validation ----------

def test_aliases_resolve_to_exactly_one_place(stores):
    rs = stores["riverside"]
    assert resolve_start("produce", rs) == resolve_start("Fresh Market", rs)
    assert resolve_start("the Dairy", rs) == resolve_start("Chilled Foods", rs)
    with pytest.raises(ValueError, match="Unknown start point 'narnia'"):
        resolve_start("narnia", rs)
    # An alias belongs to its store: Central has a "Produce" place of its own, but no "dairy" alias.
    with pytest.raises(ValueError, match="Unknown start point 'dairy'"):
        resolve_start("dairy", stores["central"])


def _with_aliases(graph, aliases_by_label: dict[str, list[str]]):
    nodes = [n.model_copy(update={"aliases": aliases_by_label.get(n.label, n.aliases)}) for n in graph.nodes]
    return graph.model_copy(update={"nodes": nodes})


def test_committed_riverside_aliases_are_valid(stores):
    rs = stores["riverside"]
    assert validators.validate_place_aliases(rs.graph, rs.products) == []
    assert {a for n in rs.graph.nodes for a in n.aliases} >= {"produce", "dairy", "bakery"}


@pytest.mark.parametrize("aliases,problem", [
    ({"Fresh Market": ["bakery"]}, "more than one place"),          # Bakehouse already has 'bakery'
    ({"Fresh Market": ["Pharmacy"]}, "is the name of a place"),       # collides with a place label
    ({"Fresh Market": ["vegetables"]}, "product word"),               # would turn product searches into starts
    ({"Fresh Market": ["fruit and veg"]}, "product word"),
    ({"Lift Lobby": ["lift"]}, "on more than one floor"),             # that label exists on both floors
    ({"Walkway 11": ["corner"]}, "walkway"),                          # junctions are not start points
    ({"Fresh Market": ["  "]}, "empty"),
])
def test_alias_collisions_are_rejected(stores, aliases, problem):
    rs = stores["riverside"]
    issues = validators.validate_place_aliases(_with_aliases(rs.graph, aliases), rs.products)
    assert any(problem in i for i in issues), issues


# ---------- API: the example from the live site ----------

def test_api_riverside_example_starts_at_fresh_market(monkeypatch):
    monkeypatch.setenv("PLANOGRAM_PROVIDER", "none")
    with TestClient(create_app()) as c:
        body = c.post("/stores/riverside/search", json={"text": "milk, eggs, brd and im at produce"}).json()
        assert [i["requested"] for i in body["items"]] == ["milk", "eggs", "brd"]
        while body["question"]:  # choose the first option for each question, as a shopper would
            q = body["question"]
            body = c.post("/stores/riverside/clarify", json={
                "session_id": body["session_id"], "item_index": q["item_index"], "sku": q["options"][0]["sku"]}).json()
        statuses = {i["requested"]: i["status"] for i in body["items"]}
        assert statuses["brd"] == "not_found"
        assert [r for r, s in statuses.items() if s != "not_found"] == ["milk", "eggs"]
        assert body["route"]["start_label"] == "Fresh Market"
