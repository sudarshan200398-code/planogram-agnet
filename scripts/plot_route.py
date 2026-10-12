"""Draw both floors with an optional route overlay.

    python scripts/plot_route.py L1_ENTRANCE L2_TOYS out.png [--accessible]
    python scripts/plot_route.py --graph-only out.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from planogram_agent.data_loader import load_dataset  # noqa: E402
from planogram_agent.graph import build_graph, shortest_path  # noqa: E402

COLORS = {"entrance": "#16a34a", "checkout": "#a855f7", "junction": "#9ca3af",
          "zone_front": "#2563eb", "aisle": "#0ea5e9", "escalator": "#f59e0b",
          "elevator": "#14b8a6", "stairs": "#78716c"}


def draw(G, gd, route, out):
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    for ax, floor in zip(axes, gd.floors):
        ax.set_title(f"Level {floor}")
        ax.set_xlim(-1, gd.bounds.width + 1)
        ax.set_ylim(-1, gd.bounds.height + 1)
        ax.set_aspect("equal")
        ax.grid(alpha=0.2)
        for u, v, d in G.edges(data=True):
            if d["kind"] == "walk" and G.nodes[u]["floor"] == floor:
                ax.plot([G.nodes[u]["x"], G.nodes[v]["x"]],
                        [G.nodes[u]["y"], G.nodes[v]["y"]], color="#d1d5db", lw=1.5, zorder=1)
        for n, d in G.nodes(data=True):
            if d["floor"] != floor:
                continue
            t = d["type"].value
            ax.scatter(d["x"], d["y"], s=60 if t != "junction" else 18,
                       color=COLORS[t], zorder=3)
            if t != "junction":
                ax.annotate(d["label"], (d["x"], d["y"]), fontsize=7,
                            xytext=(3, 4), textcoords="offset points")
        if route:
            pts = [(n, G.nodes[n]) for n in route.path if G.nodes[n]["floor"] == floor]
            for (n1, a), (n2, b) in zip(pts, pts[1:]):
                if G.has_edge(n1, n2) and G[n1][n2]["kind"] == "walk":
                    ax.plot([a["x"], b["x"]], [a["y"], b["y"]], color="#dc2626", lw=3, zorder=2)
            for n in (route.start, route.end):
                if G.nodes[n]["floor"] == floor:
                    ax.scatter(G.nodes[n]["x"], G.nodes[n]["y"], s=220, facecolors="none",
                               edgecolors="#dc2626", lw=2.5, zorder=4)
    if route:
        fig.suptitle(f"{route.start} -> {route.end} | walk {route.walking_distance} m | "
                     f"{route.floor_changes} floor change(s) via "
                     f"{[c.value for c in route.connectors_used]}"
                     f"{' | accessible only' if route.accessible_only else ''}")
    fig.tight_layout()
    fig.savefig(out, dpi=110)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("args", nargs="+")
    p.add_argument("--graph-only", action="store_true")
    p.add_argument("--accessible", action="store_true")
    a = p.parse_args()
    ds = load_dataset(ROOT / "data")
    G = build_graph(ds.graph)
    if a.graph_only:
        draw(G, ds.graph, None, a.args[0])
    else:
        start, end, out = a.args
        draw(G, ds.graph, shortest_path(G, start, end, a.accessible), out)
