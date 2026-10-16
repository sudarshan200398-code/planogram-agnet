"""Proof that Central Store and Riverside Market never mix data, sessions or images."""
from __future__ import annotations

import threading
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from planogram_agent.providers import LocalFilesProvider
from planogram_agent.settings import load_settings

STORES = ["central", "riverside"]
SVG_TITLE = "{http://www.w3.org/2000/svg}title"


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="module")
def data():
    p = LocalFilesProvider()
    out = {}
    for s in STORES:
        ds = p.load_dataset(s)
        out[s] = {"ds": ds, "skus": {x.sku for x in ds.products}, "nodes": {n.id for n in ds.graph.nodes}}
    return out


def _other(store: str) -> str:
    return "riverside" if store == "central" else "central"


@pytest.mark.parametrize("store", STORES)
def test_other_stores_skus_are_unknown(client, data, store):
    foreign = sorted(data[_other(store)]["skus"])[0]
    assert client.get(f"/stores/{store}/products/{foreign}").status_code == 404
    assert client.get(f"/stores/{store}/products/{foreign}/image").status_code == 404
    r = client.post(f"/stores/{store}/basket/route", json={"items": [{"sku": foreign, "qty": 1}]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


@pytest.mark.parametrize("store", STORES)
def test_searching_another_stores_product_never_returns_its_data(client, data, store):
    foreign = data[_other(store)]["ds"].products[3].name
    body = client.post(f"/stores/{store}/search", json={"text": foreign}).json()
    for item in body["items"]:
        assert item["sku"] is None or item["sku"] in data[store]["skus"]
    for opt in (body["question"] or {}).get("options", []):
        assert opt["sku"] in data[store]["skus"]


def test_session_from_one_store_is_unknown_in_the_other(client):
    first = client.post("/stores/central/search", json={"text": "milk"}).json()
    q = first["question"]
    r = client.post("/stores/riverside/clarify",
                    json={"session_id": first["session_id"], "item_index": q["item_index"], "sku": q["options"][0]["sku"]})
    assert r.status_code == 409
    ok = client.post("/stores/central/clarify",
                     json={"session_id": first["session_id"], "item_index": q["item_index"], "sku": q["options"][0]["sku"]})
    assert ok.status_code == 200


def test_interleaved_requests_stay_in_their_store(client, data):
    queries = {"central": "Daily Bake Plain Bagels 4 pack", "riverside": data["riverside"]["ds"].products[10].name}
    for _ in range(4):
        for store in STORES:
            body = client.post(f"/stores/{store}/search", json={"text": queries[store]}).json()
            assert body["store_id"] == store
            assert {i["sku"] for i in body["items"]} <= data[store]["skus"]
            assert set(body["route"]["path"]) <= data[store]["nodes"]
            sugg = client.get(f"/stores/{store}/suggest", params={"q": queries[store][:6]}).json()["suggestions"]
            assert {s["sku"] for s in sugg} <= data[store]["skus"]


@pytest.mark.parametrize("store", STORES)
def test_maps_categories_and_browse_belong_to_their_store(client, data, store):
    m = client.get(f"/stores/{store}/map").json()
    assert {n["id"] for n in m["nodes"]} == data[store]["nodes"]
    assert not {n["id"] for n in m["nodes"]} & data[_other(store)]["nodes"]
    page = client.get(f"/stores/{store}/products", params={"page_size": load_settings().api_page_size_max}).json()
    assert {p["sku"] for p in page["items"]} <= data[store]["skus"]


def test_image_code_always_runs_under_the_provider_lock(monkeypatch):
    """The images module keeps one process-wide product lookup, so calls into it must be serialised."""
    import planogram_agent.providers.local as local

    held: list[bool] = []
    real = local.product_image

    def spy(*args, **kwargs):
        held.append(local._IMAGE_LOCK.locked())
        return real(*args, **kwargs)

    monkeypatch.setattr(local, "product_image", spy)
    provider = LocalFilesProvider()
    for store in STORES:
        ds = provider.load_dataset(store)
        provider.product_image(store, ds.products[0].sku, ds, load_settings())
    assert held == [True, True]


def test_concurrent_image_requests_for_both_stores_never_mix():
    """End to end with threads (the race is rare, so the lock test above is the real guard)."""
    provider = LocalFilesProvider()
    settings = load_settings()
    stores = {s: provider.load_dataset(s) for s in STORES}
    errors: list[str] = []

    def worker(store: str) -> None:
        ds = stores[store]
        for prod in ds.products[:150]:
            svg = provider.product_image(store, prod.sku, ds, settings).data
            title = ET.fromstring(svg).find(SVG_TITLE).text
            if title != prod.name:
                errors.append(f"{store}: {prod.sku} drawn as {title!r}")

    threads = [threading.Thread(target=worker, args=(s,)) for s in STORES * 2]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
