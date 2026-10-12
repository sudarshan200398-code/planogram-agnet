"""Router correctness: hand-checked paths, an independent oracle, edge cases."""
import itertools
import math

import pytest

from planogram_agent.graph import (NoPathError, NodeNotFoundError, build_graph,
                                   shortest_path)
from planogram_agent.schemas import ConnectorType


def euclid(gd, a, b):
    n = {x.id: x for x in gd.nodes}
    return math.hypot(n[a].x - n[b].x, n[a].y - n[b].y)


def floyd_warshall(G, accessible_only=False):
    """Independent shortest-path oracle (no networkx path code involved)."""
    nodes = list(G.nodes)
    INF = float("inf")
    d = {a: {b: (0 if a == b else INF) for b in nodes} for a in nodes}
    for u, v, data in G.edges(data=True):
        if accessible_only and data["kind"] == "connector" and not data["accessible"]:
            continue
        d[u][v] = d[v][u] = min(d[u][v], data["weight"])
    for k in nodes:
        for i in nodes:
            for j in nodes:
                if d[i][k] + d[k][j] < d[i][j]:
                    d[i][j] = d[i][k] + d[k][j]
    return d


# ---- hand-checked cases -------------------------------------------------
def test_same_node_is_zero_length(G):
    r = shortest_path(G, "L1_PRODUCE", "L1_PRODUCE")
    assert r.path == ["L1_PRODUCE"]
    assert r.walking_distance == 0 and r.total_cost == 0
    assert r.steps == [] and r.floor_changes == 0


def test_adjacent_nodes(G, graph_data):
    r = shortest_path(G, "L1_BAKERY", "L1_DELI")
    assert r.path == ["L1_BAKERY", "L1_DELI"]
    assert r.walking_distance == pytest.approx(euclid(graph_data, "L1_BAKERY", "L1_DELI"), abs=0.01)


def test_entrance_to_produce_by_hand(G, graph_data):
    r = shortest_path(G, "L1_ENTRANCE", "L1_PRODUCE")
    assert r.path == ["L1_ENTRANCE", "L1_J_SW", "L1_PRODUCE"]
    expected = euclid(graph_data, "L1_ENTRANCE", "L1_J_SW") + euclid(graph_data, "L1_J_SW", "L1_PRODUCE")
    assert r.walking_distance == pytest.approx(expected, abs=0.01)
    assert r.floor_changes == 0 and r.connectors_used == []


def test_start_and_end_recorded(G):
    r = shortest_path(G, "L1_ENTRANCE", "L1_DAIRY")
    assert (r.start, r.end) == ("L1_ENTRANCE", "L1_DAIRY")
    assert r.path[0] == "L1_ENTRANCE" and r.path[-1] == "L1_DAIRY"


# ---- multi-floor --------------------------------------------------------
def test_cross_floor_uses_one_connector(G):
    r = shortest_path(G, "L1_ENTRANCE", "L2_TOYS")
    assert r.floor_changes == 1
    assert r.connectors_used == [ConnectorType.ESCALATOR]
    assert r.path[-1] == "L2_TOYS"
    floors = [G.nodes[n]["floor"] for n in r.path]
    assert floors == sorted(floors)  # goes up once, never back down


def test_cross_floor_cost_includes_connector(G):
    r = shortest_path(G, "L1_ENTRANCE", "L2_TOYS")
    assert r.total_cost == pytest.approx(r.walking_distance + 15, abs=0.02)


def test_downward_route_is_symmetric(G):
    up = shortest_path(G, "L1_ENTRANCE", "L2_CAFE")
    down = shortest_path(G, "L2_CAFE", "L1_ENTRANCE")
    assert up.total_cost == pytest.approx(down.total_cost)
    # Equal-cost alternatives exist (e.g. aisle 3 vs the north corridor), so the
    # reverse path may differ; it must still start/end correctly and cost the same.
    assert down.path[0] == "L2_CAFE" and down.path[-1] == "L1_ENTRANCE"
    assert down.floor_changes == up.floor_changes == 1


def test_accessible_only_uses_elevator(G):
    r = shortest_path(G, "L1_ENTRANCE", "L2_TOYS", accessible_only=True)
    assert r.connectors_used == [ConnectorType.ELEVATOR]
    assert r.accessible_only is True
    assert "L1_ESC" not in r.path and "L1_STAIRS" not in r.path


def test_accessible_route_never_cheaper(G):
    normal = shortest_path(G, "L1_ENTRANCE", "L2_TOYS")
    acc = shortest_path(G, "L1_ENTRANCE", "L2_TOYS", accessible_only=True)
    assert acc.total_cost >= normal.total_cost


def test_same_floor_route_ignores_accessible_flag(G):
    a = shortest_path(G, "L1_ENTRANCE", "L1_DAIRY")
    b = shortest_path(G, "L1_ENTRANCE", "L1_DAIRY", accessible_only=True)
    assert a.path == b.path


def test_stairs_win_when_cheaper(graph_data):
    """If the escalator is made very expensive, stairs are chosen."""
    gd = graph_data.model_copy(deep=True)
    for c in gd.connectors:
        if c.type == ConnectorType.ESCALATOR:
            c.cost = 500
    r = shortest_path(build_graph(gd), "L1_ENTRANCE", "L2_TOYS")
    assert r.connectors_used == [ConnectorType.STAIRS]


# ---- failure modes ------------------------------------------------------
def test_unknown_start_or_end(G):
    with pytest.raises(NodeNotFoundError):
        shortest_path(G, "NOPE", "L1_PRODUCE")
    with pytest.raises(NodeNotFoundError):
        shortest_path(G, "L1_PRODUCE", "NOPE")


def test_no_path_without_connectors(graph_data):
    gd = graph_data.model_copy(update={"connectors": []}, deep=True)
    with pytest.raises(NoPathError):
        shortest_path(build_graph(gd), "L1_ENTRANCE", "L2_TOYS")


def test_no_accessible_path_when_only_inaccessible_connectors(graph_data):
    gd = graph_data.model_copy(
        update={"connectors": [c for c in graph_data.connectors if not c.accessible]}, deep=True)
    G2 = build_graph(gd)
    assert shortest_path(G2, "L1_ENTRANCE", "L2_TOYS").floor_changes == 1
    with pytest.raises(NoPathError, match="accessible-only"):
        shortest_path(G2, "L1_ENTRANCE", "L2_TOYS", accessible_only=True)


def test_build_graph_rejects_unknown_edge_node(graph_data):
    from planogram_agent.schemas import Edge
    gd = graph_data.model_copy(update={"edges": graph_data.edges + [Edge(a="L1_ENTRANCE", b="X")]})
    with pytest.raises(ValueError):
        build_graph(gd)


# ---- oracle: every pair on the sample store -----------------------------
@pytest.mark.parametrize("accessible", [False, True])
def test_all_pairs_match_independent_oracle(G, accessible):
    oracle = floyd_warshall(G, accessible)
    for a, b in itertools.combinations(G.nodes, 2):
        r = shortest_path(G, a, b, accessible_only=accessible)
        assert r.total_cost == pytest.approx(oracle[a][b], abs=0.05), (a, b)


# ---- step/route consistency (directions can't invent anything) ----------
def test_steps_are_consistent_with_path(G):
    for a, b in [("L1_ENTRANCE", "L2_TOYS"), ("L2_CAFE", "L1_PRODUCE"), ("L1_BAKERY", "L1_DAIRY")]:
        r = shortest_path(G, a, b)
        assert r.steps[0].from_node == a and r.steps[-1].to_node == b
        for s1, s2 in zip(r.steps, r.steps[1:]):
            assert s1.to_node == s2.from_node
        assert sum(s.distance for s in r.steps) == pytest.approx(r.walking_distance, abs=0.05)
        assert sum(1 for s in r.steps if s.action == "take_connector") == r.floor_changes
        for s in r.steps:
            assert s.from_node in r.path and s.to_node in r.path


def test_steps_never_stop_on_plain_junctions(G):
    r = shortest_path(G, "L1_ENTRANCE", "L1_DAIRY")
    for s in r.steps[:-1]:
        assert "junction" not in G.nodes[s.to_node]["type"].value


def test_every_planogram_node_reachable_from_entrance(G, dataset):
    for e in dataset.planogram:
        shortest_path(G, "L1_ENTRANCE", e.node_id)
        shortest_path(G, "L1_ENTRANCE", e.node_id, accessible_only=True)
