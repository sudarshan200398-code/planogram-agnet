"""Floor plan rendering and route visualisation using matplotlib Figure."""
from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from planogram_agent.agents.routing import format_direction_step
from planogram_agent.autocomplete import placement_texts
from planogram_agent.schemas import NodeType

if TYPE_CHECKING:
    from planogram_agent.data_loader import Dataset
    from planogram_agent.runtime.state import Answer


def route_floor_segments(dataset: Dataset, answer: Answer | None) -> dict[int, list[tuple[str, str]]]:
    """Group consecutive route path pairs by floor; pairs that change floor belong to no floor."""
    segments: dict[int, list[tuple[str, str]]] = {}
    if not answer or not answer.route:
        return segments
    node_floor = {n.id: n.floor for n in dataset.graph.nodes}
    for u, v in itertools.pairwise(answer.route.path):
        fu, fv = node_floor.get(u), node_floor.get(v)
        if fu is not None and fu == fv:
            segments.setdefault(fu, []).append((u, v))
    return segments


def floor_change_nodes(dataset: Dataset, answer: Answer | None) -> dict[int, list[str]]:
    """Connector node ids where the route leaves or enters a floor, keyed by that node's floor."""
    changes: dict[int, list[str]] = {}
    if not answer or not answer.route:
        return changes
    node_floor = {n.id: n.floor for n in dataset.graph.nodes}
    for u, v in itertools.pairwise(answer.route.path):
        fu, fv = node_floor.get(u), node_floor.get(v)
        if fu is None or fv is None or fu == fv:
            continue
        for nid, fl in ((u, fu), (v, fv)):
            if nid not in changes.setdefault(fl, []):
                changes[fl].append(nid)
    return changes


def floor_display_order(dataset: Dataset, answer: Answer | None) -> list[int]:
    """All store floors, with the floor of the route's first stop first and the rest ascending."""
    floors = sorted(dataset.graph.floors)
    first_stops = _stop_floors(answer)
    if first_stops:
        first_floor = first_stops[0]
        if first_floor in floors:
            floors.remove(first_floor)
            floors.insert(0, first_floor)
    return floors


def _stop_floors(answer: Answer | None) -> list[int]:
    """Floor of each stop in visiting order."""
    if not answer or not answer.route:
        return []
    item_by_sku = {it.sku: it for it in answer.items if it.sku}
    floors: list[int] = []
    for sku in answer.route.ordered_skus:
        item = item_by_sku.get(sku)
        if item and item.chosen_location:
            floors.append(item.chosen_location.floor)
    return floors


def floor_change_lines(answer: Answer | None) -> list[str]:
    """Plain lines for each floor change, worded exactly as the route directions word them."""
    if not answer or not answer.route:
        return []
    return [format_direction_step(s) for s in answer.route.steps if s.kind == "take_connector"]


def clarification_option_label(dataset: Dataset, sku: str, name: str) -> str:
    """Option text with the floor and zone of each shelf placement, e.g. 'Gift Card, Level 2, Service Hub'."""
    places = placement_texts(sku, dataset)
    if not places:
        return f"{name}, no shelf location"
    return f"{name}, {' / '.join(places)}"


def get_floor_stops(answer: Answer | None, floor: int) -> list[tuple[int, str, str, str]]:
    """Return ordered list of (stop_number, sku, product_name, location_str) for given floor."""
    if not answer or not answer.route or not answer.route.ordered_skus:
        return []

    item_by_sku = {it.sku: it for it in answer.items if it.sku}
    results: list[tuple[int, str, str, str]] = []

    for idx, sku in enumerate(answer.route.ordered_skus, start=1):
        item = item_by_sku.get(sku)
        if item and item.chosen_location and item.chosen_location.floor == floor:
            name = item.name or sku
            loc = item.chosen_location
            loc_str = f"Level {loc.floor}, {loc.zone}, Bay {loc.bay}, Shelf {loc.shelf_level}"
            results.append((idx, sku, name, loc_str))

    return results


def draw_floor(dataset: Dataset, answer: Answer | None, floor: int) -> Figure:
    """Render a single store floor with walking graph and route overlay.

    Uses matplotlib.figure.Figure directly to avoid any global pyplot state.
    """
    fig = Figure(figsize=(10, 6))
    ax = fig.add_subplot(1, 1, 1)

    bounds = dataset.graph.bounds
    ax.set_xlim(-2, bounds.width + 2)
    ax.set_ylim(-2, bounds.height + 2)
    ax.set_aspect("equal")
    ax.grid(True, linestyle="--", alpha=0.25, color="#cbd5e1")

    # Map of nodes on this floor
    floor_nodes = {n.id: n for n in dataset.graph.nodes if n.floor == floor}

    # 1. Walking paths in light grey
    for edge in dataset.graph.edges:
        if edge.a in floor_nodes and edge.b in floor_nodes:
            na = floor_nodes[edge.a]
            nb = floor_nodes[edge.b]
            ax.plot(
                [na.x, nb.x],
                [na.y, nb.y],
                color="#d1d5db",
                lw=1.5,
                zorder=1,
            )

    # 2. Zone front labels and background nodes
    for n in floor_nodes.values():
        if n.type == NodeType.ZONE_FRONT:
            ax.scatter(n.x, n.y, s=30, color="#64748b", zorder=2)
            ax.annotate(
                n.label,
                (n.x, n.y),
                fontsize=7.5,
                color="#334155",
                ha="center",
                va="bottom",
                xytext=(0, 6),
                textcoords="offset points",
                zorder=4,
                bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": "none", "alpha": 0.85},
            )
        elif n.type == NodeType.CHECKOUT:
            ax.scatter(n.x, n.y, s=36, color="#8b5cf6", zorder=2)
            ax.annotate(
                n.label,
                (n.x, n.y),
                fontsize=7.5,
                color="#6d28d9",
                ha="center",
                va="bottom",
                xytext=(0, 6),
                textcoords="offset points",
                zorder=4,
                bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": "none", "alpha": 0.85},
            )

    # 3. Floor connectors marked (escalators, elevator, stairs)
    connector_types = {NodeType.ESCALATOR, NodeType.ELEVATOR, NodeType.STAIRS}
    connector_markers = {
        NodeType.ESCALATOR: ("s", "#f59e0b", "Escalator"),
        NodeType.ELEVATOR: ("D", "#0d9488", "Elevator"),
        NodeType.STAIRS: ("^", "#78716c", "Stairs"),
    }
    for n in floor_nodes.values():
        if n.type in connector_types:
            marker, color, _ = connector_markers.get(n.type, ("o", "#475569", "Connector"))
            ax.scatter(n.x, n.y, s=90, marker=marker, color=color, edgecolors="#1e293b", lw=1.2, zorder=4)
            ax.annotate(
                n.label,
                (n.x, n.y),
                fontsize=7.5,
                fontweight="bold",
                color=color,
                ha="center",
                va="top",
                xytext=(0, -6),
                textcoords="offset points",
                zorder=4,
            )

    # 4. Route points and drawing
    has_route = (
        answer is not None
        and answer.route is not None
        and bool(answer.route.path)
    )

    route_path = answer.route.path if has_route else []
    route_nodes_on_floor = [nid for nid in route_path if nid in floor_nodes]

    # Legend handles list
    legend_handles: list[Line2D] = [
        Line2D([0], [0], color="#d1d5db", lw=1.5, label="Walking path"),
    ]

    if not route_nodes_on_floor:
        ax.set_title(f"Level {floor} (no route on this floor)", fontsize=11, fontweight="bold", pad=10)
        ax.text(
            bounds.width / 2,
            bounds.height / 2,
            "no route on this floor",
            fontsize=13,
            color="#64748b",
            ha="center",
            va="center",
            bbox={"boxstyle": "round,pad=0.6", "facecolor": "#f8fafc", "edgecolor": "#cbd5e1", "lw": 1.5},
            zorder=10,
        )
    else:
        ax.set_title(f"Level {floor}", fontsize=11, fontweight="bold", pad=10)

        # 5. Draw route segments on this floor only when both ends are on this floor
        legend_handles.append(Line2D([0], [0], color="#2563eb", lw=3.0, label="Route"))
        for u, v in route_floor_segments(dataset, answer).get(floor, []):
            nu = floor_nodes[u]
            nv = floor_nodes[v]
            ax.plot([nu.x, nv.x], [nu.y, nv.y], color="#2563eb", lw=3.2, zorder=5)

        # 6. Mark connector nodes where the route changes floors
        marked_floor_change = False
        for conn_node_id in floor_change_nodes(dataset, answer).get(floor, []):
            cn = floor_nodes[conn_node_id]
            ax.scatter(
                cn.x,
                cn.y,
                s=260,
                facecolors="none",
                edgecolors="#dc2626",
                lw=2.5,
                linestyle="--",
                zorder=6,
            )
            marked_floor_change = True

        if marked_floor_change:
            legend_handles.append(
                Line2D([0], [0], marker="o", color="none", markeredgecolor="#dc2626",
                       markeredgewidth=2.0, markersize=10, linestyle="--", label="Floor change connector")
            )

        # 7. Mark the start ONLY on its own floor
        start_node_id = answer.route.start_node if answer and answer.route else None
        if start_node_id and start_node_id in floor_nodes:
            sn = floor_nodes[start_node_id]
            ax.scatter(sn.x, sn.y, s=180, color="#16a34a", marker="o", edgecolors="#14532d", lw=1.5, zorder=7)
            ax.annotate(
                "Start",
                (sn.x, sn.y),
                fontsize=8.5,
                fontweight="bold",
                color="#15803d",
                ha="right",
                va="center",
                xytext=(-8, 0),
                textcoords="offset points",
                zorder=10,
                bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": "none", "alpha": 0.85},
            )
            legend_handles.append(
                Line2D([0], [0], marker="o", color="w", markerfacecolor="#16a34a",
                       markeredgecolor="#14532d", markersize=9, label="Start point")
            )

        # 8. Numbered stop markers in visiting order
        # Where two stops share a map point show both numbers (for example "2, 3")
        item_by_sku = {it.sku: it for it in answer.items if it.sku}
        node_stops: dict[str, list[int]] = {}
        for idx, sku in enumerate(answer.route.ordered_skus, start=1):
            item = item_by_sku.get(sku)
            if item and item.chosen_location:
                node_stops.setdefault(item.chosen_location.node_id, []).append(idx)

        has_stops_on_floor = False
        for node_id, stop_nums in node_stops.items():
            if node_id in floor_nodes:
                has_stops_on_floor = True
                n = floor_nodes[node_id]
                label_text = ", ".join(str(s) for s in stop_nums)
                pad_val = 0.3 if len(label_text) <= 2 else 0.4
                ax.text(
                    n.x,
                    n.y,
                    label_text,
                    color="white",
                    fontsize=8.5,
                    fontweight="bold",
                    ha="center",
                    va="center",
                    zorder=15,
                    bbox={
                        "boxstyle": f"round,pad={pad_val}",
                        "facecolor": "#dc2626",
                        "edgecolor": "#7f1d1d",
                        "lw": 1.2,
                    },
                )

        if has_stops_on_floor:
            legend_handles.append(
                Line2D([0], [0], marker="s", color="w", markerfacecolor="#dc2626",
                       markeredgecolor="#7f1d1d", markersize=9, label="Stop (visiting order)")
            )

    ax.legend(handles=legend_handles, loc="upper right", fontsize=8, framealpha=0.9)
    fig.tight_layout()
    return fig
