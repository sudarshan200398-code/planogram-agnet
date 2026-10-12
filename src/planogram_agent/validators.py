"""Data validators. They return a list of human-readable issues (empty = valid)."""
from __future__ import annotations

import networkx as nx

from .schemas import (ConnectorType, GraphData, NodeType, PlanogramEntry,
                      Product, StockItem)

_CONNECTOR_NODE = {
    ConnectorType.ESCALATOR: NodeType.ESCALATOR,
    ConnectorType.ELEVATOR: NodeType.ELEVATOR,
    ConnectorType.STAIRS: NodeType.STAIRS,
}


class DataValidationError(Exception):
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("Data validation failed:\n- " + "\n- ".join(issues))


def assert_valid(issues: list[str]) -> None:
    if issues:
        raise DataValidationError(issues)


def validate_graph_data(data: GraphData) -> list[str]:
    issues: list[str] = []
    ids = [n.id for n in data.nodes]
    nodes = {n.id: n for n in data.nodes}

    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        issues.append(f"duplicate node ids: {sorted(dupes)}")

    for n in data.nodes:
        if n.floor not in data.floors:
            issues.append(f"node {n.id}: floor {n.floor} not in {data.floors}")
        if not (0 <= n.x <= data.bounds.width and 0 <= n.y <= data.bounds.height):
            issues.append(f"node {n.id}: ({n.x}, {n.y}) outside map bounds")

    seen_pairs: set[frozenset[str]] = set()
    for e in data.edges:
        for end in (e.a, e.b):
            if end not in nodes:
                issues.append(f"edge {e.a}-{e.b}: unknown node {end}")
        if e.a == e.b:
            issues.append(f"edge {e.a}-{e.b}: self loop")
        if e.a in nodes and e.b in nodes and nodes[e.a].floor != nodes[e.b].floor:
            issues.append(f"edge {e.a}-{e.b}: walk edge crosses floors (use a connector)")
        pair = frozenset((e.a, e.b))
        if pair in seen_pairs:
            issues.append(f"edge {e.a}-{e.b}: duplicate edge")
        seen_pairs.add(pair)

    for c in data.connectors:
        bad = False
        for end in (c.a, c.b):
            if end not in nodes:
                issues.append(f"connector {c.a}-{c.b}: unknown node {end}")
                bad = True
        if bad:
            continue
        if nodes[c.a].floor == nodes[c.b].floor:
            issues.append(f"connector {c.a}-{c.b}: both ends on floor {nodes[c.a].floor}")
        expected = _CONNECTOR_NODE[c.type]
        for end in (c.a, c.b):
            if nodes[end].type != expected:
                issues.append(
                    f"connector {c.a}-{c.b}: node {end} has type "
                    f"{nodes[end].type.value}, expected {expected.value}")
        pair = frozenset((c.a, c.b))
        if pair in seen_pairs:
            issues.append(f"connector {c.a}-{c.b}: also defined as a walk edge")

    if issues:            # structural problems make connectivity checks meaningless
        return issues

    entrances = [n.id for n in data.nodes if n.type == NodeType.ENTRANCE]
    if not entrances:
        return ["no entrance node defined"]

    full = nx.Graph()
    full.add_nodes_from(ids)
    full.add_edges_from((e.a, e.b) for e in data.edges)
    full.add_edges_from((c.a, c.b) for c in data.connectors)
    reachable = nx.node_connected_component(full, entrances[0])
    for nid in ids:
        if nid not in reachable:
            issues.append(f"node {nid} is not reachable from the entrance")

    accessible = nx.Graph()
    accessible.add_nodes_from(ids)
    accessible.add_edges_from((e.a, e.b) for e in data.edges)
    accessible.add_edges_from((c.a, c.b) for c in data.connectors if c.accessible)
    acc_reach = nx.node_connected_component(accessible, entrances[0])
    for nid in ids:
        if nid in reachable and nid not in acc_reach:
            issues.append(f"node {nid} is not reachable in accessible-only mode")
    return issues


def validate_products(products: list[Product]) -> list[str]:
    skus = [p.sku for p in products]
    dupes = {s for s in skus if skus.count(s) > 1}
    issues = [f"duplicate product sku: {s}" for s in sorted(dupes)]
    if not products:
        issues.append("product table is empty")
    return issues


def validate_planogram(entries: list[PlanogramEntry], products: list[Product],
                       data: GraphData) -> list[str]:
    issues: list[str] = []
    nodes = {n.id: n for n in data.nodes}
    skus = {p.sku for p in products}
    seen_slots: set[tuple] = set()
    for e in entries:
        if e.sku not in skus:
            issues.append(f"planogram: sku {e.sku} not in product table")
        if e.node_id not in nodes:
            issues.append(f"planogram: sku {e.sku} -> unknown node {e.node_id}")
        else:
            node = nodes[e.node_id]
            if node.floor != e.floor:
                issues.append(f"planogram: sku {e.sku} floor {e.floor} but node "
                              f"{e.node_id} is on floor {node.floor}")
            if node.type == NodeType.JUNCTION:
                issues.append(f"planogram: sku {e.sku} placed on junction {e.node_id}")
        slot = (e.node_id, e.bay, e.shelf_level, e.position)
        if slot in seen_slots:
            issues.append(f"planogram: two products share slot {slot}")
        seen_slots.add(slot)
    return issues


def validate_inventory(stock: list[StockItem], products: list[Product]) -> list[str]:
    skus = {p.sku for p in products}
    issues = [f"inventory: unknown sku {s.sku}" for s in stock if s.sku not in skus]
    ids = [s.sku for s in stock]
    issues += [f"inventory: duplicate sku {s}" for s in sorted({i for i in ids if ids.count(i) > 1})]
    return issues
