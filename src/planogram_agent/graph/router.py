"""Shortest-path routing across floors (Dijkstra over the whole building)."""
from __future__ import annotations

import networkx as nx

from ..schemas import ConnectorType, NodeType, Route, Step


class RouterError(Exception):
    pass


class NodeNotFoundError(RouterError):
    pass


class NoPathError(RouterError):
    pass


def _view(G: nx.Graph, accessible_only: bool) -> nx.Graph:
    if not accessible_only:
        return G

    def ok(u, v):
        d = G[u][v]
        return d["kind"] == "walk" or d.get("accessible", False)

    return nx.subgraph_view(G, filter_edge=ok)


def shortest_path(G: nx.Graph, start: str, end: str,
                  accessible_only: bool = False) -> Route:
    for nid in (start, end):
        if nid not in G:
            raise NodeNotFoundError(f"unknown node: {nid}")

    H = _view(G, accessible_only)
    try:
        path = nx.dijkstra_path(H, start, end, weight="weight")
    except nx.NetworkXNoPath as exc:
        mode = " (accessible-only)" if accessible_only else ""
        raise NoPathError(f"no path from {start} to {end}{mode}") from exc

    return _build_route(G, path, accessible_only)


def _build_route(G: nx.Graph, path: list[str], accessible_only: bool) -> Route:
    steps: list[Step] = []
    walk_start = path[0]
    walk_dist = 0.0
    walking_total = 0.0
    total_cost = 0.0
    connectors: list[ConnectorType] = []

    def flush(to_node: str) -> None:
        nonlocal walk_start, walk_dist
        if walk_dist > 0:
            steps.append(Step(
                action="walk", from_node=walk_start, to_node=to_node,
                from_label=G.nodes[walk_start]["label"],
                to_label=G.nodes[to_node]["label"],
                distance=round(walk_dist, 2),
                floor_from=G.nodes[walk_start]["floor"],
                floor_to=G.nodes[to_node]["floor"]))
        walk_start, walk_dist = to_node, 0.0

    for u, v in zip(path, path[1:]):
        edge = G[u][v]
        total_cost += edge["weight"]
        if edge["kind"] == "connector":
            flush(u)
            connectors.append(edge["connector_type"])
            steps.append(Step(
                action="take_connector", from_node=u, to_node=v,
                from_label=G.nodes[u]["label"], to_label=G.nodes[v]["label"],
                distance=0.0, floor_from=G.nodes[u]["floor"],
                floor_to=G.nodes[v]["floor"], connector_type=edge["connector_type"]))
            walk_start = v
        else:
            walk_dist += edge["distance"]
            walking_total += edge["distance"]
            # end a walking leg at the next named place (skip plain junctions)
            if G.nodes[v]["type"] != NodeType.JUNCTION:
                flush(v)
    flush(path[-1])  # no-op when the last node already closed the leg

    return Route(
        start=path[0], end=path[-1], path=path,
        walking_distance=round(walking_total, 2),
        total_cost=round(total_cost, 2),
        floor_changes=len(connectors), connectors_used=connectors,
        accessible_only=accessible_only, steps=steps)
