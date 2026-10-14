"""Tests for arrive steps generation and ordering in routing and trip plans."""
from __future__ import annotations

from pathlib import Path
import pytest

from planogram_agent.data_loader import load_dataset
from planogram_agent.agents.routing import plan_trip
from planogram_agent.settings import Settings

STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(STORE_DIR, validate=True)


@pytest.fixture(scope="module")
def settings():
    return Settings()


def _verify_arrive_step_contract(res, expected_skus: list[str]) -> None:
    """Validate that every ordered SKU has exactly one arrive step in correct order."""
    assert res.trip_plan.ordered_skus == expected_skus

    arrive_steps = [s for s in res.directions if s.kind == "arrive"]
    assert len(arrive_steps) == len(expected_skus), (
        f"Expected {len(expected_skus)} arrive steps, but got {len(arrive_steps)}: {res.directions}"
    )
    assert [s.sku for s in arrive_steps] == expected_skus

    # Verify no 'Walk 0m'
    assert "Walk 0m" not in res.directions_text

    # Verify each product name is in directions_text
    for s in arrive_steps:
        assert s.product_name in res.directions_text

    # Verify ordering: arrive steps for products at start node come first, before any walk/connector
    first_non_arrive_idx = next(
        (i for i, s in enumerate(res.directions) if s.kind != "arrive"),
        None,
    )
    if first_non_arrive_idx is not None:
        # Steps before first_non_arrive must all be arrive steps at start_node
        for s in res.directions[:first_non_arrive_idx]:
            assert s.kind == "arrive"
            # In store_demo, L1_BAKERY label is 'Bakery'
            assert s.from_label == res.directions[first_non_arrive_idx].from_label or s.to_label == res.directions[first_non_arrive_idx].from_label


def test_standing_at_bakery_asking_for_bakery_plus_cafe_product(dataset, settings):
    """Case 1: standing at Bakery asking for a bakery product plus a Café product (original scenario a)."""
    # BAK-BAG-009 is in Bakery (L1_BAKERY), CAF-BUL-014 is in Café (L2_CAFE)
    res = plan_trip(dataset, start_text="Bakery", skus=["BAK-BAG-009", "CAF-BUL-014"], settings=settings)
    _verify_arrive_step_contract(res, ["BAK-BAG-009", "CAF-BUL-014"])

    # Arrive step for Bakery product must be step 1 before walking
    assert res.directions[0].kind == "arrive"
    assert res.directions[0].sku == "BAK-BAG-009"
    assert res.directions[-1].kind == "arrive"
    assert res.directions[-1].sku == "CAF-BUL-014"


def test_two_products_at_the_same_stop(dataset, settings):
    """Case 2: two products at the same stop."""
    # BAK-TOR-001 and BAK-TOR-002 are both at Bakery (L1_BAKERY)
    res = plan_trip(dataset, start_text="Entrance", skus=["BAK-TOR-001", "BAK-TOR-002"], settings=settings)
    _verify_arrive_step_contract(res, ["BAK-TOR-001", "BAK-TOR-002"])

    # Both arrive steps should be at the end of the trip
    arrive_steps = [s for s in res.directions if s.kind == "arrive"]
    assert len(arrive_steps) == 2
    assert res.directions[-2].kind == "arrive"
    assert res.directions[-1].kind == "arrive"


def test_product_shelved_in_two_places_one_at_start_node(dataset, settings):
    """Case 3: a product shelved in two places where one location is at the start node."""
    # BAK-FRE-004 is in Bakery (L1_BAKERY) and Café (L2_CAFE).
    # Starting at Bakery with PRO-APP-001 (Produce L1_PRODUCE), planner picks Bakery location for BAK-FRE-004.
    res = plan_trip(dataset, start_text="Bakery", skus=["BAK-FRE-004", "PRO-APP-001"], settings=settings)
    _verify_arrive_step_contract(res, ["BAK-FRE-004", "PRO-APP-001"])

    # BAK-FRE-004 arrive step must come first before walking to Produce
    assert res.directions[0].kind == "arrive"
    assert res.directions[0].sku == "BAK-FRE-004"
    assert res.directions[0].to_label == "Bakery"


def test_start_node_equal_to_only_stop(dataset, settings):
    """Case 4: the start node equal to the only stop."""
    res = plan_trip(dataset, start_text="Bakery", skus=["BAK-BAG-009"], settings=settings)
    _verify_arrive_step_contract(res, ["BAK-BAG-009"])
    assert len(res.directions) == 1
    assert res.directions[0].kind == "arrive"
    assert res.directions[0].sku == "BAK-BAG-009"


def test_three_stop_trip_middle_stop_has_two_products(dataset, settings):
    """Case 5: a three-stop trip where the middle stop has two products."""
    # Start: Entrance (L1_ENTRANCE)
    # Stop 1: Produce (PRO-APP-001)
    # Stop 2: Bakery (BAK-TOR-001, BAK-TOR-002)
    # Stop 3: Café (CAF-BUL-014)
    res = plan_trip(
        dataset,
        start_text="Entrance",
        skus=["PRO-APP-001", "BAK-TOR-001", "BAK-TOR-002", "CAF-BUL-014"],
        settings=settings,
    )
    _verify_arrive_step_contract(res, ["PRO-APP-001", "BAK-TOR-001", "BAK-TOR-002", "CAF-BUL-014"])

    # Check legs and arrive steps interleaving
    arrive_indices = [i for i, s in enumerate(res.directions) if s.kind == "arrive"]
    assert len(arrive_indices) == 4
    # Produce arrive is before Bakery arrive
    assert res.directions[arrive_indices[0]].sku == "PRO-APP-001"
    # Bakery arrives are consecutive
    assert arrive_indices[2] == arrive_indices[1] + 1
    assert {res.directions[arrive_indices[1]].sku, res.directions[arrive_indices[2]].sku} == {"BAK-TOR-001", "BAK-TOR-002"}
    # Café arrive is last
    assert res.directions[arrive_indices[3]].sku == "CAF-BUL-014"
