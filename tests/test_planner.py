"""Unit tests for Phase 5 multi-product route planner."""
from pathlib import Path

import pytest

from planogram_agent.data_loader import load_dataset
from planogram_agent.graph import build_graph, shortest_path
from planogram_agent.planner import TripPlan, plan_route
from planogram_agent.schemas import ConnectorType
from planogram_agent.settings import Settings

STORE_DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(STORE_DEMO_DIR, validate=True)


@pytest.fixture(scope="module")
def G(dataset):
    return build_graph(dataset.graph)


def test_one_product_equals_existing_single_route(dataset, G):
    """One product equals the existing single route from start to destination."""
    sku = "BAK-BAG-001"  # at L1_BAKERY
    start_node = "L1_ENTRANCE"

    single_route = shortest_path(G, start_node, "L1_BAKERY", accessible_only=False)
    plan = plan_route(dataset, start_node, [sku], accessible_only=False)

    assert isinstance(plan, TripPlan)
    assert plan.ordered_skus == [sku]
    assert len(plan.legs) == 1
    assert plan.legs[0].start == single_route.start
    assert plan.legs[0].end == single_route.end
    assert plan.legs[0].path == single_route.path
    assert plan.total_cost == single_route.total_cost
    assert plan.walking_distance == single_route.walking_distance
    assert plan.floor_changes == single_route.floor_changes
    assert plan.connectors_used == single_route.connectors_used
    assert plan.unlocated_skus == []


def test_two_products_on_same_floor(dataset):
    """Two products on the same floor result in 0 floor changes and sum of leg costs."""
    skus = ["BAK-BAG-001", "DAI-PAC-002"]  # L1_BAKERY, L1_DAIRY
    plan = plan_route(dataset, "L1_ENTRANCE", skus)

    assert plan.floor_changes == 0
    assert plan.connectors_used == []
    assert len(plan.legs) == 2
    assert set(plan.ordered_skus) == set(skus)
    # Total cost must equal sum of leg costs
    assert plan.total_cost == round(sum(l.total_cost for l in plan.legs), 2)
    assert plan.walking_distance == round(sum(l.walking_distance for l in plan.legs), 2)


def test_products_on_both_floors(dataset):
    """Products on both floors navigate vertical connectors and record floor changes."""
    skus = ["BAK-BAG-001", "CAF-PRE-003"]  # L1_BAKERY (floor 1), L2_CAFE (floor 2)
    plan = plan_route(dataset, "L1_ENTRANCE", skus)

    assert plan.floor_changes >= 1
    assert len(plan.connectors_used) >= 1
    assert len(plan.legs) == 2
    assert set(plan.ordered_skus) == set(skus)
    assert plan.total_cost == round(sum(l.total_cost for l in plan.legs), 2)


def test_two_products_at_same_point(dataset):
    """Several products at the same map point count as one stop."""
    # HOU-TRA-001 and HOU-TRA-002 are both shelved at L2_HOUSEHOLD
    skus = ["HOU-TRA-001", "HOU-TRA-002"]
    plan = plan_route(dataset, "L1_ENTRANCE", skus)

    assert len(plan.legs) == 1
    assert plan.legs[0].end == "L2_HOUSEHOLD"
    assert len(plan.ordered_skus) == 2
    assert plan.ordered_skus == ["HOU-TRA-001", "HOU-TRA-002"]
    assert plan.total_cost == plan.legs[0].total_cost


def test_product_with_two_locations_picks_cheaper_one(dataset):
    """If a product is shelved in more than one place, pick combination with lowest total cost."""
    # BAK-FRE-004 is shelved at L1_BAKERY (cost 33.04 from entrance) and L2_CAFE (cost 141.24)
    sku = "BAK-FRE-004"
    plan = plan_route(dataset, "L1_ENTRANCE", [sku])

    assert len(plan.legs) == 1
    assert plan.legs[0].end == "L1_BAKERY"
    assert plan.total_cost == 33.04
    assert plan.ordered_skus == [sku]


def test_accessible_only_avoids_stairs_and_escalators(dataset):
    """Accessible-only mode avoids stairs and escalators across all legs."""
    skus = ["CAF-PRE-003"]  # L2_CAFE
    plan = plan_route(dataset, "L1_ENTRANCE", skus, accessible_only=True)

    assert plan.floor_changes >= 1
    assert len(plan.connectors_used) >= 1
    for connector in plan.connectors_used:
        assert connector == ConnectorType.ELEVATOR
        assert connector != ConnectorType.STAIRS
        assert connector != ConnectorType.ESCALATOR


def test_start_point_equal_to_stop(dataset):
    """A start point equal to a stop yields zero total cost and walking distance."""
    # BAK-TOR-001 is at L1_BAKERY
    plan = plan_route(dataset, "L1_BAKERY", ["BAK-TOR-001"])

    assert plan.total_cost == 0.0
    assert plan.walking_distance == 0.0
    assert plan.floor_changes == 0
    assert plan.connectors_used == []
    assert len(plan.legs) == 1
    assert plan.legs[0].start == "L1_BAKERY"
    assert plan.legs[0].end == "L1_BAKERY"
    assert plan.ordered_skus == ["BAK-TOR-001"]


def test_empty_list(dataset):
    """An empty sku list returns zero costs and empty legs."""
    plan = plan_route(dataset, "L1_ENTRANCE", [])

    assert plan.ordered_skus == []
    assert plan.legs == []
    assert plan.total_cost == 0.0
    assert plan.walking_distance == 0.0
    assert plan.floor_changes == 0
    assert plan.connectors_used == []
    assert plan.unlocated_skus == []


def test_unlocated_sku_reporting(dataset):
    """SKUs with no location are skipped and reported in unlocated_skus."""
    skus = ["NON-EXISTENT-SKU", "BAK-BAG-001"]
    plan = plan_route(dataset, "L1_ENTRANCE", skus)

    assert plan.unlocated_skus == ["NON-EXISTENT-SKU"]
    assert plan.ordered_skus == ["BAK-BAG-001"]
    assert len(plan.legs) == 1


def test_fallback_when_max_evaluations_exceeded(dataset):
    """When estimated evaluations exceed max_plan_evaluations, use greedy fallback."""
    # Force max_plan_evaluations=1 to trigger fallback
    low_limit_settings = Settings(max_plan_evaluations=1)
    skus = ["BAK-BAG-001", "DAI-PAC-002", "BAK-FRE-004"]
    plan = plan_route(dataset, "L1_ENTRANCE", skus, settings=low_limit_settings)

    assert isinstance(plan, TripPlan)
    assert set(plan.ordered_skus) == set(skus)
    assert plan.total_cost == round(sum(l.total_cost for l in plan.legs), 2)
    # BAK-FRE-004 has locations at L1_BAKERY and L2_CAFE; nearest location to previous stop is chosen
    assert "L1_BAKERY" in [l.end for l in plan.legs]


def test_deterministic_tie_breaking(dataset):
    """The exact same input called twice produces an identical result."""
    skus = ["BAK-BAG-001", "DAI-PAC-002", "DEL-BUL-002"]
    plan1 = plan_route(dataset, "L1_ENTRANCE", skus)
    plan2 = plan_route(dataset, "L1_ENTRANCE", skus)

    assert plan1.ordered_skus == plan2.ordered_skus
    assert plan1.total_cost == plan2.total_cost
    assert plan1.walking_distance == plan2.walking_distance
    assert plan1.floor_changes == plan2.floor_changes
    assert plan1.connectors_used == plan2.connectors_used
    assert [l.path for l in plan1.legs] == [l.path for l in plan2.legs]
