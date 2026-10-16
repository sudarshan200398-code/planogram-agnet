"""Store registry and data providers: LocalFilesProvider (used) and the HttpProvider stub (not wired)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from planogram_agent.data_loader import load_dataset
from planogram_agent.interface import create_finder, create_finder_for_dataset
from planogram_agent.llm.no_model import NoModelClient
from planogram_agent.providers import (
    HttpProvider,
    LocalFilesProvider,
    StoreDataProvider,
    StoreInfo,
    StoreNotFoundError,
)
from planogram_agent.settings import load_settings
from planogram_agent.validators import DataValidationError

ROOT = Path(__file__).resolve().parent.parent
STORE_FILES = ("graph.json", "products.csv", "planogram.csv", "inventory.csv")


@pytest.fixture(scope="module")
def provider():
    return LocalFilesProvider()


def _registry(tmp_path: Path, stores: list[dict]) -> Path:
    path = tmp_path / "stores.json"
    path.write_text(json.dumps({"stores": stores}), encoding="utf-8")
    return path


def _copy_store(src: Path, dst: Path, with_prices: bool) -> Path:
    dst.mkdir(parents=True)
    for f in STORE_FILES:
        shutil.copy(src / f, dst / f)
    if with_prices:
        shutil.copy(src / "prices.csv", dst / "prices.csv")
    return dst


# ---------- registry ----------


def test_registry_lists_both_stores(provider):
    assert provider.list_stores() == [
        StoreInfo(id="central", name="Central Store"),
        StoreInfo(id="riverside", name="Riverside Market"),
    ]
    raw = json.loads((ROOT / "config" / "stores.json").read_text(encoding="utf-8"))
    assert [s["data_dir"] for s in raw["stores"]] == ["data/store_demo", "data/store_riverside"]


def test_local_provider_satisfies_the_interface(provider):
    assert isinstance(provider, StoreDataProvider)


@pytest.mark.parametrize("store_id, folder", [("central", "store_demo"), ("riverside", "store_riverside")])
def test_load_dataset_matches_the_folder(provider, store_id, folder):
    ds = provider.load_dataset(store_id)
    direct = load_dataset(ROOT / "data" / folder, validate=True)
    assert [p.sku for p in ds.products] == [p.sku for p in direct.products]
    assert [n.id for n in ds.graph.nodes] == [n.id for n in direct.graph.nodes]


@pytest.mark.parametrize("bad", ["nope", "", "CENTRAL", "../central"])
def test_unknown_store_id(provider, bad):
    with pytest.raises(StoreNotFoundError):
        provider.load_dataset(bad)


def test_registry_rejects_duplicate_ids_and_bad_ids(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        LocalFilesProvider(_registry(tmp_path, [
            {"id": "a", "name": "A", "data_dir": str(ROOT / "data" / "store_demo")},
            {"id": "a", "name": "B", "data_dir": str(ROOT / "data" / "store_riverside")},
        ]))
    with pytest.raises(ValueError, match="id"):
        LocalFilesProvider(_registry(tmp_path, [{"id": "Bad Id!", "name": "X", "data_dir": "x"}]))


def test_registry_file_from_environment(tmp_path, monkeypatch):
    path = _registry(tmp_path, [{"id": "only", "name": "Only", "data_dir": str(ROOT / "data" / "store_riverside")}])
    monkeypatch.setenv("PLANOGRAM_STORES_FILE", str(path))
    assert [s.id for s in LocalFilesProvider().list_stores()] == ["only"]


def test_missing_store_folder_fails_on_load_not_on_start(tmp_path):
    p = LocalFilesProvider(_registry(tmp_path, [{"id": "gone", "name": "Gone", "data_dir": str(tmp_path / "nope")}]))
    assert [s.id for s in p.list_stores()] == ["gone"]
    with pytest.raises(FileNotFoundError):
        p.load_dataset("gone")


# ---------- prices (optional) ----------


def test_prices_loaded_when_present(provider):
    ds = provider.load_dataset("central")
    prices = provider.load_prices("central", ds)
    assert len(prices) == len(ds.products)
    assert all(isinstance(v, float) and v > 0 for v in prices.values())


def test_prices_absent_gives_empty_mapping(tmp_path):
    folder = _copy_store(ROOT / "data" / "store_demo", tmp_path / "s", with_prices=False)
    p = LocalFilesProvider(_registry(tmp_path, [{"id": "s", "name": "S", "data_dir": str(folder)}]))
    assert p.load_prices("s", p.load_dataset("s")) == {}


@pytest.mark.parametrize(
    "rows, problem",
    [
        ("sku,price\nNOT-A-SKU,10.00\n", "unknown sku"),
        ("sku,price\nGA1-SPE-001,-1\n", "price"),
        ("sku,price\nGA1-SPE-001,abc\n", "price"),
        ("sku,price\nGA1-SPE-001,10\nGA1-SPE-001,11\n", "duplicate"),
        ("sku,cost\nGA1-SPE-001,10\n", "header"),
    ],
)
def test_bad_prices_file_is_rejected(tmp_path, rows, problem):
    folder = _copy_store(ROOT / "data" / "store_demo", tmp_path / "s", with_prices=False)
    (folder / "prices.csv").write_text(rows, encoding="utf-8")
    p = LocalFilesProvider(_registry(tmp_path, [{"id": "s", "name": "S", "data_dir": str(folder)}]))
    with pytest.raises(DataValidationError, match=problem):
        p.load_prices("s", p.load_dataset("s"))


# ---------- images ----------


def test_product_image_placeholder_and_real_file(tmp_path):
    folder = _copy_store(ROOT / "data" / "store_riverside", tmp_path / "r", with_prices=True)
    p = LocalFilesProvider(_registry(tmp_path, [{"id": "r", "name": "R", "data_dir": str(folder)}]))
    ds = p.load_dataset("r")
    sku = ds.products[0].sku
    settings = load_settings()
    assert p.product_image("r", sku, ds, settings).source == "placeholder"
    (folder / "images").mkdir()
    Image.new("RGB", (40, 40), "red").save(folder / "images" / f"{sku}.png")
    assert p.product_image("r", sku, ds, settings).source == "file"


# ---------- HttpProvider stub ----------


def test_http_provider_is_a_documented_stub():
    stub = HttpProvider(base_url="https://example.invalid/api", api_key_env="COMPANY_API_KEY")
    assert isinstance(stub, StoreDataProvider)
    assert "GET" in (HttpProvider.__doc__ or "")
    for call in (
        lambda: stub.list_stores(),
        lambda: stub.load_dataset("central"),
        lambda: stub.load_prices("central", None),
        lambda: stub.product_image("central", "SKU", None, load_settings()),
    ):
        with pytest.raises(NotImplementedError):
            call()


def test_http_provider_is_not_wired_into_the_api():
    for path in (ROOT / "api").rglob("*.py"):
        assert "HttpProvider" not in path.read_text(encoding="utf-8"), path


# ---------- engine construction from a dataset ----------


def test_create_finder_for_dataset_matches_create_finder():
    folder = ROOT / "data" / "store_demo"
    a = create_finder(folder, client=NoModelClient())
    b = create_finder_for_dataset(load_dataset(folder, validate=True), client=NoModelClient())
    assert [p.sku for p in a.dataset.products] == [p.sku for p in b.dataset.products]
    assert a.settings == b.settings and a.model_note == b.model_note
    assert a.run("Daily Bake Plain Bagels 4 pack").route.ordered_skus == b.run("Daily Bake Plain Bagels 4 pack").route.ordered_skus
