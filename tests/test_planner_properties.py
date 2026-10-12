"""Property-style tests for Phase 5 multi-product route planner."""
import itertools
import random
from pathlib import Path

import pytest

from planogram_agent.data_loader import load_dataset
from planogram_agent.graph import build_graph, shortest_path
from planogram_agent.planner import plan_route
from planogram_agent.tools import get_location

STORE_DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(STORE_DEMO_DIR, validate=True)


@pytest.fixture(scope="module")
def G(dataset):
    return build_graph(dataset.graph)


@pytest.fixture(scope="module")
def single_location_products(dataset):
    """Map of node_id -> sku for products with exactly one fixed placement."""
    node_to_sku = {}
    for p in dataset.products:
        locs = get_location(p.sku, dataset)
        if len(locs) == 1:
            nid = locs[0].node_id
            if nid not in node_to_sku:
                node_to_sku[nid] = p.sku
    return node_to_sku


@pytest.mark.parametrize("num_stops", [2, 3, 4, 5, 6])
def test_property_exact_matches_brute_force_up_to_6_stops(
    dataset, G, single_location_products, num_stops
):
    """For lists of up to 6 stops the plan equals a brute-force best order."""
    rng = random.Random(42 + num_stops)
    available_nodes = sorted(single_location_products.keys())
    chosen_nodes = rng.sample(available_nodes, num_stops)
    skus = [single_location_products[n] for n in chosen_nodes]
    start_node = "L1_ENTRANCE"

    plan = plan_route(dataset, start_node, skus)

    # Independent brute-force evaluation of all permutations
    cache = {}

    def leg_cost(u: str, v: str) -> float:
        if (u, v) not in cache:
            cache[(u, v)] = shortest_path(G, u, v).total_cost
        return cache[(u, v)]

    min_brute_force = float("inf")
    for perm in itertools.permutations(chosen_nodes):
        cost = leg_cost(start_node, perm[0])
        for i in range(len(perm) - 1):
            cost += leg_cost(perm[i], perm[i + 1])
        cost = round(cost, 2)
        min_brute_force = min(min_brute_force, cost)

    assert plan.total_cost == pytest.approx(min_brute_force, abs=1e-2)


@pytest.mark.parametrize("num_stops", [9, 10, 11, 12])
def test_property_heuristic_within_5_percent_of_2000_random_orders(
    dataset, G, single_location_products, num_stops
):
    """For 9 to 12 stops the heuristic cost is within 5% of the best of 2000 random orders."""
    rng = random.Random(100 + num_stops)
    available_nodes = sorted(single_location_products.keys())
    chosen_nodes = rng.sample(available_nodes, num_stops)
    skus = [single_location_products[n] for n in chosen_nodes]
    start_node = "L1_ENTRANCE"

    plan = plan_route(dataset, start_node, skus)

    cache = {}

    def leg_cost(u: str, v: str) -> float:
        if (u, v) not in cache:
            cache[(u, v)] = shortest_path(G, u, v).total_cost
        return cache[(u, v)]

    # Sample 2000 random orders
    min_random_cost = float("inf")
    for _ in range(2000):
        order = list(chosen_nodes)
        rng.shuffle(order)
        cost = leg_cost(start_node, order[0])
        for i in range(len(order) - 1):
            cost += leg_cost(order[i], order[i + 1])
        cost = round(cost, 2)
        min_random_cost = min(min_random_cost, cost)

    # Heuristic cost must be within 5% of (or beat) best random order
    assert plan.total_cost <= min_random_cost * 1.05 + 1e-4
