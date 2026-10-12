"""Turn validated GraphData into a networkx graph covering all floors."""
from __future__ import annotations

import math

import networkx as nx

from ..schemas import GraphData


def build_graph(data: GraphData) -> nx.Graph:
    """One graph for the whole building.

    Walk edges have kind="walk" and weight = metres.
    Connector edges have kind="connector", weight = cost, plus type/accessible.
    """
    G = nx.Graph(store_id=data.store_id)
    for n in data.nodes:
        G.add_node(n.id, floor=n.floor, x=n.x, y=n.y, type=n.type, label=n.label)

    for e in data.edges:
        for end in (e.a, e.b):
            if end not in G:
                raise ValueError(f"edge {e.a}-{e.b} references unknown node {end}")
        d = e.distance
        if d is None:
            a, b = G.nodes[e.a], G.nodes[e.b]
            d = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
        G.add_edge(e.a, e.b, kind="walk", weight=d, distance=d)

    for c in data.connectors:
        for end in (c.a, c.b):
            if end not in G:
                raise ValueError(f"connector {c.a}-{c.b} references unknown node {end}")
        G.add_edge(c.a, c.b, kind="connector", weight=c.cost, distance=0.0,
                   connector_type=c.type, accessible=c.accessible)
    return G
