"""Tiny CLI for manual checks:  python -m planogram_agent.cli L1_ENTRANCE L2_TOYS [--accessible]"""
from __future__ import annotations

import argparse

from .data_loader import load_dataset
from .graph import build_graph, shortest_path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("start")
    p.add_argument("end")
    p.add_argument("--accessible", action="store_true")
    p.add_argument("--data", default="data")
    a = p.parse_args()

    G = build_graph(load_dataset(a.data).graph)
    r = shortest_path(G, a.start, a.end, accessible_only=a.accessible)
    print(f"{r.start} -> {r.end}: walk {r.walking_distance} m, "
          f"{r.floor_changes} floor change(s), cost {r.total_cost}")
    for i, s in enumerate(r.steps, 1):
        if s.action == "walk":
            print(f" {i}. Walk {s.distance} m: {s.from_label} -> {s.to_label}")
        else:
            print(f" {i}. Take the {s.connector_type.value}: "
                  f"Level {s.floor_from} -> Level {s.floor_to}")


if __name__ == "__main__":
    main()
