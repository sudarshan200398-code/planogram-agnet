"""Unit tests for Phase 6b Search, Availability, and Routing agents."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from planogram_agent.agents.availability import Availability, check_availability
from planogram_agent.agents.routing import (
    DirectionStep,
    RoutingResult,
    build_direction_steps,
    format_directions,
    plan_trip,
)
from planogram_agent.agents.search import MatchResult, match_item
from planogram_agent.data_loader import load_dataset
from planogram_agent.pipeline_lite import run_pipeline_lite
from planogram_agent.settings import load_settings

STORE_DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(STORE_DEMO_DIR, validate=True)


@pytest.fixture(scope="module")
def settings():
    return load_settings()


from planogram_agent.runtime.consistency import check_directions_consistency


# =====================================================================
# 1. Search Agent Tests
# =====================================================================

def test_search_matched_exact(dataset, settings):
    res = match_item("Store Brand Baseball Cap one size", dataset, settings)
    assert isinstance(res, MatchResult)
    assert res.status == "matched"
    assert res.chosen is not None
    assert res.chosen.sku == "APP-ACC-004"
    assert res.options == []


def test_search_ambiguous_two_to_three_options_no_unrelated(dataset, settings):
    res = match_item("milk", dataset, settings)
    assert isinstance(res, MatchResult)
    assert res.status == "ambiguous"
    assert res.chosen is None
    assert 2 <= len(res.options) <= 3
    # Check that all options have valid SKUs from dataset
    valid_skus = {p.sku for p in dataset.products}
    for opt in res.options:
        assert opt.sku in valid_skus
        assert "milk" in opt.name.lower() or "noodle" in opt.name.lower() or "mix" in opt.name.lower() or opt.score >= settings.ask_threshold


def test_search_not_found(dataset, settings):
    res = match_item("quantum flux capacitor", dataset, settings)
    assert isinstance(res, MatchResult)
    assert res.status == "not_found"
    assert res.chosen is None
    assert res.options == []


def test_search_result_only_contains_existing_skus(dataset, settings):
    valid_skus = {p.sku for p in dataset.products}
    res = match_item("bread", dataset, settings)
    if res.chosen:
        assert res.chosen.sku in valid_skus
    for opt in res.options:
        assert opt.sku in valid_skus


# =====================================================================
# 2. Availability Agent Tests
# =====================================================================

def test_availability_in_stock(dataset):
    res = check_availability("BAK-BAG-001", dataset)
    assert isinstance(res, Availability)
    assert res.status == "available"
    assert res.quantity > 0
    assert res.reason is None


def test_availability_out_of_stock(dataset):
    # TOY-ART-005 is quantity 0 in inventory.csv
    res = check_availability("TOY-ART-005", dataset)
    assert isinstance(res, Availability)
    assert res.status == "unavailable"
    assert res.quantity == 0
    assert res.reason == "Out of stock"


def test_availability_unknown_sku(dataset):
    res = check_availability("UNKNOWN-SKU-999", dataset)
    assert isinstance(res, Availability)
    assert res.status == "unknown"
    assert res.quantity == 0
    assert res.reason is not None
    assert "not found" in res.reason.lower()


# =====================================================================
# 3. Routing Agent Tests
# =====================================================================

def test_routing_resolve_start_various_landmarks(dataset, settings):
    # None resolves to entrance
    res_none = plan_trip(dataset, start_text=None, skus=["BAK-BAG-001"], settings=settings)
    assert res_none.start_node == "L1_ENTRANCE"

    # Specific landmark on Level 1
    res_bakery = plan_trip(dataset, start_text="Bakery", skus=["DAI-PAC-002"], settings=settings)
    assert res_bakery.start_node == "L1_BAKERY"

    # Multi-floor landmark with explicit floor
    res_esc_l2 = plan_trip(dataset, start_text="Escalators", floor=2, skus=["CAF-BUL-014"], settings=settings)
    assert res_esc_l2.start_node == "L2_ESC"

    # Multi-floor landmark without floor raises ValueError
    with pytest.raises(ValueError, match="multiple floors"):
        plan_trip(dataset, start_text="Escalators", floor=None, skus=["CAF-BUL-014"], settings=settings)

    # Unknown landmark raises ValueError
    with pytest.raises(ValueError, match="Unknown start point"):
        plan_trip(dataset, start_text="NonExistentPlace", skus=["BAK-BAG-001"], settings=settings)


def test_routing_arrive_step_uses_planner_chosen_stop_for_multi_shelved_product(dataset, settings):
    # BAK-FRE-004 is shelved in two places: L1_BAKERY (floor 1) and L2_CAFE (floor 2).
    # Starting from Entrance, L1_BAKERY is much closer (cost 33.04 vs 141.24).
    res = plan_trip(dataset, start_text="Entrance", skus=["BAK-FRE-004"], settings=settings)
    assert len(res.directions) > 0

    arrive_steps = [s for s in res.directions if s.kind == "arrive"]
    assert len(arrive_steps) == 1
    arrive = arrive_steps[0]
    assert arrive.sku == "BAK-FRE-004"
    assert arrive.floor == 1
    assert "Bakery" in arrive.to_label
    assert "Level 1" in arrive.location_text
    assert "Bakery" in arrive.location_text


def test_routing_two_products_at_same_stop_produces_two_arrive_steps(dataset, settings):
    # HOU-TRA-001 and HOU-TRA-002 are both shelved at L2_HOUSEHOLD
    res = plan_trip(dataset, start_text="Entrance", skus=["HOU-TRA-001", "HOU-TRA-002"], settings=settings)
    arrive_steps = [s for s in res.directions if s.kind == "arrive"]
    assert len(arrive_steps) == 2
    skus = [s.sku for s in arrive_steps]
    assert skus == ["HOU-TRA-001", "HOU-TRA-002"]
    for arrive in arrive_steps:
        assert arrive.floor == 2
        assert "Level 2" in arrive.location_text
        assert "Household" in arrive.location_text


def test_routing_merges_connector_step(dataset, settings):
    # Entrance (floor 1) to Toys (floor 2) requires the escalator or stairs
    res = plan_trip(dataset, start_text="Entrance", skus=["TOY-ACT-001"], accessible_only=False, settings=settings)
    connector_steps = [s for s in res.directions if s.kind == "take_connector"]
    assert len(connector_steps) >= 1
    conn = connector_steps[0]
    assert conn.floor == 1
    assert conn.to_floor == 2
    assert "Take the escalator from Level 1 to Level 2." in res.directions_text


def test_routing_consistency_checker(dataset, settings):
    res = plan_trip(dataset, start_text="Entrance", skus=["TOY-ACT-001", "BAK-BAG-001"], settings=settings)
    is_valid, errors = check_directions_consistency(res.directions, res.directions_text)
    assert is_valid, f"Consistency checker failed: {errors}"


def test_routing_consistency_checker_detects_corruptions():
    step = DirectionStep(
        kind="walk",
        floor=1,
        from_label="Entrance",
        to_label="Bakery",
        distance=33.04,
    )
    # Correct text has 33m
    correct_text = "1. Walk 33m from Entrance to Bakery."
    ok, _ = check_directions_consistency([step], correct_text)
    assert ok

    # Wrong distance
    wrong_dist_text = "1. Walk 50m from Entrance to Bakery."
    bad_dist_ok, errs = check_directions_consistency([step], wrong_dist_text)
    assert not bad_dist_ok
    assert any("Distance mismatch" in e for e in errs)

    # Missing label
    bad_label_text = "1. Walk 33m from Entrance to SomewhereElse."
    bad_label_ok, errs = check_directions_consistency([step], bad_label_text)
    assert not bad_label_ok
    assert any("missing to_label" in e for e in errs)


def test_routing_unlocated_skus_read_from_trip_plan(dataset, settings):
    res = plan_trip(dataset, start_text="Entrance", skus=["UNLOCATED-SKU-999"], settings=settings)
    assert isinstance(res, RoutingResult)
    assert res.unlocated_skus == ["UNLOCATED-SKU-999"]
    assert res.trip_plan.unlocated_skus == ["UNLOCATED-SKU-999"]
    assert res.directions == []
    assert res.directions_text == ""


# =====================================================================
# 4. Pipeline Lite End-to-End Tests
# =====================================================================

def test_pipeline_lite_out_of_stock_excluded_from_route(dataset, settings):
    # OOS-01: ArtBox Watercolour Paints 12 pack (TOY-ART-005) is out of stock
    res = run_pipeline_lite("ArtBox Watercolour Paints 12 pack", dataset, settings)
    assert res.response_status == "partial"
    assert len(res.items) == 1
    assert res.items[0].status == "matched"
    assert res.items[0].chosen_sku == "TOY-ART-005"
    assert res.items[0].availability == "unavailable"
    assert res.routing is None


def test_pipeline_lite_mixed_out_of_stock_and_available(dataset, settings):
    # MIX-01: CUS-BRO-008 is available, BAK-PIE-008 is out of stock, quantum flux capacitor not found
    q = "Store Brand Warranty Claim Pad 25 sheets, Golden Crust Cheesecake Slice 1 slice and quantum flux capacitor"
    res = run_pipeline_lite(q, dataset, settings)
    assert res.response_status == "partial"
    assert len(res.items) == 3

    # Check item statuses
    assert res.items[0].status == "matched" and res.items[0].chosen_sku == "CUS-BRO-008" and res.items[0].availability == "available"
    assert res.items[1].status == "matched" and res.items[1].chosen_sku == "BAK-PIE-008" and res.items[1].availability == "unavailable"
    assert res.items[2].status == "not_found"

    # Only available item CUS-BRO-008 is routed
    assert res.routing is not None
    assert res.routing.trip_plan.ordered_skus == ["CUS-BRO-008"]
