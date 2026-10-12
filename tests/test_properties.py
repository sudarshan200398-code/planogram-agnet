"""Property-based checks of the router with hypothesis."""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from planogram_agent.data_loader import load_dataset
from planogram_agent.graph import build_graph, shortest_path
from tests.conftest import DATA

_G = build_graph(load_dataset(DATA).graph)
NODES = sorted(_G.nodes)
node = st.sampled_from(NODES)


@settings(max_examples=150, deadline=None)
@given(node, node)
def test_symmetry(a, b):
    assert shortest_path(_G, a, b).total_cost == pytest.approx(shortest_path(_G, b, a).total_cost)


@settings(max_examples=150, deadline=None)
@given(node, node, node)
def test_triangle_inequality(a, b, c):
    ab = shortest_path(_G, a, b).total_cost
    bc = shortest_path(_G, b, c).total_cost
    ac = shortest_path(_G, a, c).total_cost
    # Route costs are rounded to 2 dp, so allow 3 x 0.005 of rounding slack.
    assert ac <= ab + bc + 0.02


@settings(max_examples=150, deadline=None)
@given(node, node, st.booleans())
def test_route_endpoints_and_nonnegative(a, b, acc):
    r = shortest_path(_G, a, b, accessible_only=acc)
    assert r.path[0] == a and r.path[-1] == b
    assert r.walking_distance >= 0 and r.total_cost >= r.walking_distance - 0.02
    assert (r.total_cost == 0) == (a == b)
