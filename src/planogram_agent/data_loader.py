"""Load and validate the store dataset from disk."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .schemas import GraphData, PlanogramEntry, Product, StockItem
from .validators import (assert_valid, validate_graph_data, validate_inventory,
                         validate_place_aliases, validate_planogram, validate_products)


@dataclass
class Dataset:
    graph: GraphData
    products: list[Product]
    planogram: list[PlanogramEntry]
    inventory: list[StockItem]


def load_graph_data(path: Path) -> GraphData:
    return GraphData.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def _rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_products(path: Path) -> list[Product]:
    out = []
    for r in _rows(path):
        out.append(Product(
            sku=r["sku"], name=r["name"], brand=r["brand"] or None,
            category=r["category"], size=r["size"] or None,
            keywords=[k for k in r["keywords"].split("|") if k]))
    return out


def load_planogram(path: Path) -> list[PlanogramEntry]:
    return [PlanogramEntry(
        sku=r["sku"], floor=int(r["floor"]), zone=r["zone"], bay=r["bay"],
        shelf_level=int(r["shelf_level"]), position=int(r["position"]),
        node_id=r["node_id"]) for r in _rows(path)]


def load_inventory(path: Path) -> list[StockItem]:
    return [StockItem(sku=r["sku"], quantity=int(r["quantity"])) for r in _rows(path)]


def load_dataset(data_dir: Path | str = "data", validate: bool = True) -> Dataset:
    d = Path(data_dir)
    ds = Dataset(
        graph=load_graph_data(d / "graph.json"),
        products=load_products(d / "products.csv"),
        planogram=load_planogram(d / "planogram.csv"),
        inventory=load_inventory(d / "inventory.csv"),
    )
    if validate:
        assert_valid(
            validate_graph_data(ds.graph)
            + validate_products(ds.products)
            + validate_planogram(ds.planogram, ds.products, ds.graph)
            + validate_inventory(ds.inventory, ds.products)
            + validate_place_aliases(ds.graph, ds.products))
    return ds


def load_golden_queries(path: Path | str = "tests/golden_queries.json") -> dict:
    p = Path(path)
    if not p.is_file():
        candidate = Path(__file__).resolve().parent.parent.parent / p
        if candidate.is_file():
            p = candidate
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

