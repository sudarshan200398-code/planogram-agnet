"""Unit tests for Phase 4 lookup tools and product matching."""
from pathlib import Path

import pytest

from planogram_agent.data_loader import load_dataset
from planogram_agent.settings import Settings
from planogram_agent.tools import (
    Candidate,
    Location,
    check_inventory,
    decide_match,
    get_location,
    normalize_text,
    resolve_start,
    search_products,
)

STORE_DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"


@pytest.fixture(scope="module")
def demo_dataset():
    return load_dataset(STORE_DEMO_DIR, validate=True)


@pytest.fixture(scope="module")
def settings():
    return Settings(accept_threshold=0.85, ask_threshold=0.5, margin=0.1, top_k=5)


# --- Text Normalization Tests ---

def test_normalize_text_units():
    assert normalize_text("500g") == normalize_text("500 g")
    assert normalize_text("1kg") == normalize_text("1 kg")
    assert normalize_text("2L") == normalize_text("2 l")
    assert normalize_text("10pack") == normalize_text("10 pack")


def test_normalize_text_casing_and_accents():
    assert normalize_text("Café") == "cafe"
    assert normalize_text("UPPERCASE") == "uppercase"


def test_normalize_text_punctuation():
    assert normalize_text("Tomato & Basil, Sauce!") == "tomato basil sauce"


def test_normalize_text_plurals():
    assert normalize_text("batteries") == "battery"
    assert normalize_text("wraps") == "wrap"
    assert normalize_text("cookies") == "cookie"
    assert normalize_text("onions") == "onion"


# --- Search Products Tests ---

def test_search_products_exact(demo_dataset):
    candidates = search_products("Store Brand Baseball Cap one size", top_k=5, dataset=demo_dataset)
    assert len(candidates) > 0
    top = candidates[0]
    assert top.sku == "APP-ACC-004"
    assert top.score >= 0.95


def test_search_products_typo(demo_dataset):
    candidates = search_products("Daiy Bake Whole Wheat Wraps 10 pack", top_k=5, dataset=demo_dataset)
    assert len(candidates) > 0
    top = candidates[0]
    assert top.sku == "BAK-TOR-007"
    assert top.score >= 0.85


def test_search_products_synonym(demo_dataset):
    candidates = search_products("Golden Crust doughnut 6 pack", top_k=5, dataset=demo_dataset)
    assert len(candidates) > 0
    top = candidates[0]
    assert top.sku == "BAK-MUF-003"
    assert top.score >= 0.9


def test_search_products_size_narrows(demo_dataset):
    cands_std = search_products("Chicken Sandwich standard", top_k=5, dataset=demo_dataset)
    assert cands_std[0].sku == "CAF-PRE-001"
    assert cands_std[0].score >= 0.85

    cands_lg = search_products("Chicken Sandwich large", top_k=5, dataset=demo_dataset)
    assert cands_lg[0].sku == "CAF-PRE-002"
    assert cands_lg[0].score >= 0.85


def test_search_products_not_found(demo_dataset):
    candidates = search_products("quantum flux capacitor", top_k=5, dataset=demo_dataset)
    assert len(candidates) == 0 or candidates[0].score < 0.5


# --- Decide Match Tests ---

def test_decide_match_matched(demo_dataset, settings):
    candidates = [
        Candidate(sku="SKU-1", name="Store Brand Product One 500 g", score=0.92),
        Candidate(sku="SKU-2", name="Store Brand Product Two 500 g", score=0.75),
    ]
    decision = decide_match(candidates, settings, demo_dataset, query="Store Brand Product One 500 g")
    assert decision.status == "matched"
    assert len(decision.candidates) == 1
    assert decision.candidates[0].sku == "SKU-1"


def test_decide_match_small_gap_ambiguous(demo_dataset, settings):
    candidates = [
        Candidate(sku="SKU-1", name="Product One", score=0.90),
        Candidate(sku="SKU-2", name="Product Two", score=0.86),  # Gap is 0.04 < margin 0.1
    ]
    decision = decide_match(candidates, settings, demo_dataset, query="Product")
    assert decision.status == "ambiguous"
    assert len(decision.candidates) == 2


def test_decide_match_generic_ambiguous(demo_dataset, settings):
    # Query 'milk' matches multiple products and has no brand or size narrowing it
    candidates = search_products("milk", top_k=5, dataset=demo_dataset)
    decision = decide_match(candidates, settings, demo_dataset, query="milk")
    assert decision.status == "ambiguous"
    assert len(decision.candidates) == 3


def test_decide_match_not_found(demo_dataset, settings):
    candidates = [
        Candidate(sku="SKU-1", name="Random Product", score=0.35),
    ]
    decision = decide_match(candidates, settings, demo_dataset, query="Nonexistent")
    assert decision.status == "not_found"
    assert decision.candidates == []


def test_decide_match_two_matching_products_gives_two_options(demo_dataset, settings):
    # Exactly 2 products above ask_threshold, plus unrelated/low candidates
    candidates = [
        Candidate(sku="SKU-1", name="Product One", score=0.75),
        Candidate(sku="SKU-2", name="Product Two", score=0.70),
        Candidate(sku="SKU-3", name="Unrelated", score=0.20),
        Candidate(sku="SKU-4", name="Zero Match", score=0.0),
    ]
    decision = decide_match(candidates, settings, demo_dataset, query="Product")
    assert decision.status == "ambiguous"
    assert len(decision.candidates) == 2
    assert [c.sku for c in decision.candidates] == ["SKU-1", "SKU-2"]


def test_decide_match_five_matching_products_gives_three_options(demo_dataset, settings):
    # 5 products all above ask_threshold -> must cap at top 3
    candidates = [
        Candidate(sku="SKU-1", name="Product One", score=0.82),
        Candidate(sku="SKU-2", name="Product Two", score=0.80),
        Candidate(sku="SKU-3", name="Product Three", score=0.78),
        Candidate(sku="SKU-4", name="Product Four", score=0.75),
        Candidate(sku="SKU-5", name="Product Five", score=0.70),
    ]
    decision = decide_match(candidates, settings, demo_dataset, query="Product")
    assert decision.status == "ambiguous"
    assert len(decision.candidates) == 3
    assert [c.sku for c in decision.candidates] == ["SKU-1", "SKU-2", "SKU-3"]


def test_decide_match_single_weak_candidate_gives_one_option(demo_dataset, settings):
    # Single candidate above ask_threshold (0.5) but below accept_threshold (0.85)
    candidates = [
        Candidate(sku="SKU-1", name="Product One", score=0.70),
        Candidate(sku="SKU-2", name="Unrelated Product", score=0.30),
    ]
    decision = decide_match(candidates, settings, demo_dataset, query="Product One")
    assert decision.status == "ambiguous"
    assert len(decision.candidates) == 1
    assert decision.candidates[0].sku == "SKU-1"


def test_decide_match_no_candidate_above_ask_threshold_gives_not_found(demo_dataset, settings):
    candidates = [
        Candidate(sku="SKU-1", name="Product One", score=0.45),
        Candidate(sku="SKU-2", name="Product Two", score=0.30),
    ]
    decision = decide_match(candidates, settings, demo_dataset, query="Product")
    assert decision.status == "not_found"
    assert decision.candidates == []


# --- Check Inventory Tests ---

def test_check_inventory_available(demo_dataset):
    status = check_inventory("APP-ACC-004", demo_dataset)
    assert status == "available"


def test_check_inventory_unavailable(demo_dataset):
    # TOY-ART-005 has quantity 0 in store_demo
    status = check_inventory("TOY-ART-005", demo_dataset)
    assert status == "unavailable"


def test_check_inventory_unknown(demo_dataset):
    status = check_inventory("NON-EXISTENT-SKU", demo_dataset)
    assert status == "unknown"


# --- Get Location Tests ---

def test_get_location_found(demo_dataset):
    locations = get_location("APP-ACC-004", demo_dataset)
    assert len(locations) >= 1
    loc = locations[0]
    assert isinstance(loc, Location)
    assert loc.floor == 2
    assert loc.zone == "Apparel & Clothing"
    assert loc.bay == "D"
    assert loc.shelf_level == 4
    assert loc.node_id == "L2_APPAREL_E"


def test_get_location_unplaced(demo_dataset):
    locations = get_location("UNPLACED-SKU", demo_dataset)
    assert locations == []


# --- Resolve Start Tests ---

def test_resolve_start_empty(demo_dataset):
    assert resolve_start("", demo_dataset) == "L1_ENTRANCE"
    assert resolve_start(None, demo_dataset) == "L1_ENTRANCE"
    assert resolve_start("   ", demo_dataset) == "L1_ENTRANCE"


def test_resolve_start_named_location(demo_dataset):
    assert resolve_start("Bakery", demo_dataset) == "L1_BAKERY"
    assert resolve_start("the Bakery", demo_dataset) == "L1_BAKERY"
    assert resolve_start("bAkErY", demo_dataset) == "L1_BAKERY"
    assert resolve_start("Produce", demo_dataset) == "L1_PRODUCE"


def test_cafe_label_and_resolve_start(demo_dataset):
    cafe_node = next(n for n in demo_dataset.graph.nodes if n.id == "L2_CAFE")
    assert cafe_node.label == "Café"
    assert resolve_start("Café", demo_dataset) == "L2_CAFE"
    assert resolve_start("the café", demo_dataset) == "L2_CAFE"


def test_resolve_start_multi_floor_with_floor(demo_dataset):
    assert resolve_start("Escalators", demo_dataset, floor=1) == "L1_ESC"
    assert resolve_start("Escalators", demo_dataset, floor=2) == "L2_ESC"
    assert resolve_start("Elevator", demo_dataset, floor=1) == "L1_ELV"
    assert resolve_start("Elevator", demo_dataset, floor=2) == "L2_ELV"


def test_resolve_start_multi_floor_without_floor_raises(demo_dataset):
    with pytest.raises(ValueError) as excinfo:
        resolve_start("Escalators", demo_dataset, floor=None)
    err = str(excinfo.value)
    assert "multiple floors" in err
    assert "Escalators (Level 1)" in err
    assert "Escalators (Level 2)" in err


def test_resolve_start_unknown_raises(demo_dataset):
    with pytest.raises(ValueError) as excinfo:
        resolve_start("Nowhere Zone", demo_dataset)
    err = str(excinfo.value)
    assert "Unknown start point 'Nowhere Zone'" in err
    assert "Valid names:" in err
    assert "Bakery" in err
