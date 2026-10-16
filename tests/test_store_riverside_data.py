"""Store 2 (Riverside Market) data, the synthetic price files, and Store 1 left untouched."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
from pathlib import Path

import pytest

from planogram_agent.data_loader import load_dataset
from planogram_agent.schemas import ConnectorType, NodeType

ROOT = Path(__file__).resolve().parent.parent
CENTRAL = ROOT / "data" / "store_demo"
RIVERSIDE = ROOT / "data" / "store_riverside"
STORE_FILES = ("graph.json", "products.csv", "planogram.csv", "inventory.csv")

# Store 1 files as they were before this phase (line endings normalised); they must never change.
CENTRAL_HASHES = {
    "README.md": "411ad99fe02155878252f34a24b4e4745838f3b75f77f69441b1f649a1226133",
    "graph.json": "05ffecbdb95b78e896483a6a2a8c42fced416b72b8a50d1577e1828bb2a8a7d3",
    "inventory.csv": "5789b297cbfb1f9997dfed5c6debb8725d5483b59b8bb7404e132fdd5f739ee7",
    "planogram.csv": "c535b280222ff794f4f000003a986024761c137854c6922d8892f89ec6e4b47b",
    "products.csv": "c6090d41871fb40ecdf50ea7ce1f2932af0ec0a950e62ac4cbbe0ff42f67b25e",
    "store_map.png": "bb05b2db77213968a7852e952f1688c8eb83e168219ee4c7ff52670693e40d96",
}


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _norm_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    return data if path.suffix == ".png" else data.replace(b"\r\n", b"\n")


@pytest.fixture(scope="module")
def central():
    return load_dataset(CENTRAL, validate=True)


@pytest.fixture(scope="module")
def riverside():
    return load_dataset(RIVERSIDE, validate=True)


# ---------- Store 1 untouched ----------


@pytest.mark.parametrize("name", sorted(CENTRAL_HASHES))
def test_central_store_files_unchanged(name):
    assert hashlib.sha256(_norm_bytes(CENTRAL / name)).hexdigest() == CENTRAL_HASHES[name]


# ---------- Store 2 shape ----------


def test_riverside_passes_validators_and_has_two_floors(riverside):
    assert riverside.graph.floors == [1, 2]
    assert riverside.graph.store_id == "riverside"


def test_riverside_connectors(riverside):
    by_type = {c.type: c for c in riverside.graph.connectors}
    assert set(by_type) == {ConnectorType.ESCALATOR, ConnectorType.STAIRS, ConnectorType.ELEVATOR}
    assert by_type[ConnectorType.ELEVATOR].accessible is True
    assert by_type[ConnectorType.ESCALATOR].accessible is False
    assert by_type[ConnectorType.STAIRS].accessible is False


def test_riverside_has_entrance_checkout_and_zones_on_both_floors(riverside):
    nodes = riverside.graph.nodes
    assert sum(n.type == NodeType.ENTRANCE for n in nodes) == 1
    assert sum(n.type == NodeType.CHECKOUT for n in nodes) == 1
    for floor in (1, 2):
        assert sum(n.type in (NodeType.ZONE_FRONT, NodeType.AISLE) and n.floor == floor for n in nodes) >= 6


def test_riverside_products_placed_and_stocked(riverside):
    assert len(riverside.products) >= 400
    skus = {p.sku for p in riverside.products}
    assert skus == {e.sku for e in riverside.planogram}
    assert skus == {s.sku for s in riverside.inventory}
    qty = [s.quantity for s in riverside.inventory]
    assert any(q == 0 for q in qty) and sum(q > 0 for q in qty) > 0.9 * len(qty)


def test_riverside_shares_nothing_with_central(central, riverside):
    assert all(p.sku.startswith("RS-") for p in riverside.products)
    assert not {p.sku for p in central.products} & {p.sku for p in riverside.products}
    assert not {p.name.lower() for p in central.products} & {p.name.lower() for p in riverside.products}
    assert not {(p.brand or "").lower() for p in central.products} & {(p.brand or "").lower() for p in riverside.products}
    assert not {n.id for n in central.graph.nodes} & {n.id for n in riverside.graph.nodes}
    labels = lambda ds: {n.label.lower() for n in ds.graph.nodes if n.type != NodeType.JUNCTION}  # noqa: E731
    assert not labels(central) & labels(riverside)


def test_riverside_generator_is_deterministic(tmp_path):
    gen = _script("generate_store_riverside")
    gen.generate(tmp_path / "a")
    gen.generate(tmp_path / "b")
    for name in (*STORE_FILES, "prices.csv", "README.md"):
        first = _norm_bytes(tmp_path / "a" / name)
        assert first == _norm_bytes(tmp_path / "b" / name), name
        assert first == _norm_bytes(RIVERSIDE / name), f"{name} differs from the committed store"


def test_riverside_readme_says_synthetic():
    text = (RIVERSIDE / "README.md").read_text(encoding="utf-8").lower()
    assert "synthetic" in text and "prices.csv" in text


# ---------- prices (optional, synthetic) ----------


def _prices(folder: Path) -> dict[str, str]:
    with open(folder / "prices.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows and list(rows[0]) == ["sku", "price"]
    return {r["sku"]: r["price"] for r in rows}


@pytest.mark.parametrize("store", ["central", "riverside"])
def test_prices_cover_every_product_with_positive_rupees(store, central, riverside):
    ds, folder = (central, CENTRAL) if store == "central" else (riverside, RIVERSIDE)
    prices = _prices(folder)
    assert set(prices) == {p.sku for p in ds.products}
    for value in prices.values():
        assert float(value) > 0 and value == f"{float(value):.2f}"


def test_central_prices_script_is_deterministic_and_new_file_only(tmp_path):
    prices = _script("generate_store_prices")
    prices.write_prices(CENTRAL / "products.csv", tmp_path / "prices.csv")
    assert _norm_bytes(tmp_path / "prices.csv") == _norm_bytes(CENTRAL / "prices.csv")
    note = (CENTRAL / "PRICES.md").read_text(encoding="utf-8").lower()
    assert "synthetic" in note
