"""HTTP API: every endpoint on both stores, errors, limits, middleware. FastAPI TestClient, no network."""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.main import create_app
from planogram_agent.providers import LocalFilesProvider
from planogram_agent.settings import load_settings
from planogram_agent.tools import check_inventory, get_location

ROOT = Path(__file__).resolve().parent.parent
STORES = ["central", "riverside"]
STORE_FILES = ("graph.json", "products.csv", "planogram.csv", "inventory.csv")
BAGELS = "Daily Bake Plain Bagels 4 pack"


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="module")
def datasets():
    p = LocalFilesProvider()
    return {s: p.load_dataset(s) for s in STORES}


def _single_place(ds, floor: int):
    """First in-stock product with exactly one shelf location, on the given floor."""
    for p in sorted(ds.products, key=lambda p: p.sku):
        locs = get_location(p.sku, ds)
        if len(locs) == 1 and locs[0].floor == floor and check_inventory(p.sku, ds) == "available":
            return p
    raise AssertionError("no such product")


def _error(resp, status: int, code: str) -> dict:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == resp.headers["X-Request-ID"]
    return body["error"]


PRODUCT_FIELDS = {"sku", "name", "brand", "category", "size", "price", "currency", "stock_status", "in_stock",
                  "floor", "zone", "bay", "shelf", "locations", "image_url"}


def _check_product(prod: dict, store: str, ds) -> None:
    assert PRODUCT_FIELDS <= set(prod)
    assert prod["image_url"] == f"/stores/{store}/products/{prod['sku']}/image"
    assert prod["currency"] == "INR"
    inv = next(i.quantity for i in ds.inventory if i.sku == prod["sku"])
    assert prod["in_stock"] == inv
    assert prod["stock_status"] == ("in_stock" if inv > 0 else "out_of_stock")
    locs = get_location(prod["sku"], ds)
    assert [(l["floor"], l["zone"], l["bay"], l["shelf"], l["node_id"]) for l in prod["locations"]] == [
        (l.floor, l.zone, l.bay, l.shelf_level, l.node_id) for l in locs
    ]
    assert (prod["floor"], prod["zone"]) == (locs[0].floor, locs[0].zone)


# ---------- health, stores, docs ----------


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert [s["id"] for s in r.json()["stores"]] == STORES


def test_stores(client, datasets):
    r = client.get("/stores")
    assert r.status_code == 200
    assert r.json() == [
        {"id": "central", "name": "Central Store", "floors": [1, 2], "product_count": len(datasets["central"].products),
         "has_prices": True},
        {"id": "riverside", "name": "Riverside Market", "floors": [1, 2],
         "product_count": len(datasets["riverside"].products), "has_prices": True},
    ]


def test_docs_and_openapi(client):
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    for path in ("/health", "/stores", "/stores/{store_id}/categories", "/stores/{store_id}/products",
                 "/stores/{store_id}/suggest", "/stores/{store_id}/search", "/stores/{store_id}/clarify",
                 "/stores/{store_id}/products/{sku}", "/stores/{store_id}/basket/route", "/stores/{store_id}/map",
                 "/stores/{store_id}/products/{sku}/image"):
        assert path in paths, path


# ---------- categories and browsing ----------


@pytest.mark.parametrize("store", STORES)
def test_categories(client, datasets, store):
    r = client.get(f"/stores/{store}/categories")
    assert r.status_code == 200
    cats = r.json()["categories"]
    assert [c["name"] for c in cats] == sorted({p.category for p in datasets[store].products}, key=str.casefold)
    assert sum(c["product_count"] for c in cats) == len(datasets[store].products)


@pytest.mark.parametrize("store", STORES)
def test_browse_category_pages_are_stable_and_complete(client, datasets, store):
    ds = datasets[store]
    cat = max({p.category for p in ds.products}, key=lambda c: sum(p.category == c for p in ds.products))
    expected = sorted((p for p in ds.products if p.category == cat), key=lambda p: (p.name.casefold(), p.sku))
    got = []
    page = 1
    while True:
        r = client.get(f"/stores/{store}/products", params={"category": cat, "page": page, "page_size": 3})
        assert r.status_code == 200
        body = r.json()
        assert (body["store_id"], body["category"], body["page"], body["page_size"], body["total"]) == (
            store, cat, page, 3, len(expected))
        if not body["items"]:
            break
        for prod in body["items"]:
            _check_product(prod, store, ds)
        got += [p["sku"] for p in body["items"]]
        page += 1
    assert got == [p.sku for p in expected]
    again = client.get(f"/stores/{store}/products", params={"category": cat, "page": 1, "page_size": 3}).json()
    assert [p["sku"] for p in again["items"]] == got[:3]


def test_browse_all_products_and_page_size_cap(client, datasets):
    settings = load_settings()
    r = client.get("/stores/central/products")
    assert r.status_code == 200
    assert r.json()["page_size"] == settings.api_page_size_default
    assert r.json()["total"] == len(datasets["central"].products)
    ok = client.get("/stores/central/products", params={"page_size": settings.api_page_size_max})
    assert ok.status_code == 200 and len(ok.json()["items"]) == settings.api_page_size_max
    _error(client.get("/stores/central/products", params={"page_size": settings.api_page_size_max + 1}),
           422, "VALIDATION_ERROR")
    _error(client.get("/stores/central/products", params={"page": 0}), 422, "VALIDATION_ERROR")
    _error(client.get("/stores/central/products", params={"category": "No Such Category"}), 404, "CATEGORY_NOT_FOUND")


# ---------- suggest and product ----------


@pytest.mark.parametrize("store, q", [("central", "bre"), ("riverside", "man")])
def test_suggest(client, datasets, store, q):
    r = client.get(f"/stores/{store}/suggest", params={"q": q})
    assert r.status_code == 200
    rows = r.json()["suggestions"]
    assert 0 < len(rows) <= load_settings().autocomplete_limit
    skus = {p.sku for p in datasets[store].products}
    for row in rows:
        assert row["sku"] in skus
        assert row["image_url"] == f"/stores/{store}/products/{row['sku']}/image"
        assert row["label"].startswith(row["name"])
    assert client.get(f"/stores/{store}/suggest", params={"q": "x"}).json()["suggestions"] == []
    _error(client.get(f"/stores/{store}/suggest", params={"q": "a" * 501}), 422, "TEXT_TOO_LONG")


@pytest.mark.parametrize("store", STORES)
def test_product_detail(client, datasets, store):
    ds = datasets[store]
    prod = ds.products[5]
    r = client.get(f"/stores/{store}/products/{prod.sku}")
    assert r.status_code == 200
    body = r.json()
    _check_product(body, store, ds)
    assert (body["name"], body["brand"], body["category"]) == (prod.name, prod.brand, prod.category)
    assert isinstance(body["price"], float) and body["price"] > 0
    _error(client.get(f"/stores/{store}/products/NOPE-000"), 404, "PRODUCT_NOT_FOUND")


@pytest.mark.parametrize("store", STORES)
def test_product_image(client, datasets, store):
    prod = datasets[store].products[0]
    r = client.get(f"/stores/{store}/products/{prod.sku}/image")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert prod.name.split()[0] in r.text
    _error(client.get(f"/stores/{store}/products/NOPE-000/image"), 404, "PRODUCT_NOT_FOUND")


# ---------- search and clarify ----------


SEARCH_FIELDS = {"store_id", "status", "session_id", "verified", "messages", "items", "question", "route"}
ITEM_FIELDS = PRODUCT_FIELDS | {"index", "requested", "quantity_requested", "status", "reason"}
ROUTE_FIELDS = {"start_node", "start_label", "total_distance_m", "floor_changes", "accessible_only", "steps",
                "stops", "segments", "path"}


def test_search_central_ok_has_everything_a_front_end_needs(client, datasets):
    r = client.post("/stores/central/search", json={"text": BAGELS})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == SEARCH_FIELDS
    assert (body["store_id"], body["status"], body["verified"], body["question"]) == ("central", "ok", True, None)
    item = body["items"][0]
    assert set(item) == ITEM_FIELDS
    assert (item["sku"], item["name"], item["status"], item["quantity_requested"]) == ("BAK-BAG-009", BAGELS, "available", 1)
    _check_product(item, "central", datasets["central"])
    assert isinstance(item["price"], float)
    route = body["route"]
    assert set(route) == ROUTE_FIELDS
    assert route["start_label"] == "Entrance" and route["total_distance_m"] > 0
    assert [s["number"] for s in route["steps"]] == list(range(1, len(route["steps"]) + 1))
    assert route["steps"][-1]["kind"] == "arrive" and route["steps"][-1]["icon"] == "location_on"
    assert route["stops"][0]["sku"] == "BAK-BAG-009"
    assert route["segments"] and all(len(line) == 2 for seg in route["segments"] for line in seg["lines"])


def test_search_clarify_flow_central(client):
    first = client.post("/stores/central/search", json={"text": "milk"}).json()
    assert first["status"] == "needs_clarification" and first["route"] is None
    q = first["question"]
    assert q["item_text"] == "milk" and len(q["options"]) >= 2
    opt = q["options"][0]
    assert {"sku", "name", "places", "image_url"} <= set(opt)
    r = client.post("/stores/central/clarify",
                    json={"session_id": first["session_id"], "item_index": q["item_index"], "sku": opt["sku"]})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["items"][0]["sku"] == opt["sku"] and body["route"]["steps"]
    _error(client.post("/stores/central/clarify",
                       json={"session_id": first["session_id"], "item_index": q["item_index"], "sku": opt["sku"]}),
           409, "SESSION_NOT_FOUND")


def test_clarify_errors(client):
    _error(client.post("/stores/central/clarify", json={"session_id": "nope", "item_index": 0, "sku": "X"}),
           409, "SESSION_NOT_FOUND")
    first = client.post("/stores/central/search", json={"text": "milk"}).json()
    sid, q = first["session_id"], first["question"]
    _error(client.post("/stores/central/clarify", json={"session_id": sid, "item_index": 9, "sku": q["options"][0]["sku"]}),
           422, "INVALID_CHOICE")
    _error(client.post("/stores/central/clarify", json={"session_id": sid, "item_index": q["item_index"], "sku": "BAK-BAG-009"}),
           422, "INVALID_CHOICE")


def test_search_riverside_start_phrase_and_floors(client, datasets):
    ds = datasets["riverside"]
    upstairs = _single_place(ds, 2)
    r = client.post("/stores/riverside/search", json={"text": f"im at fresh market, {upstairs.name}"})
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ok"
    assert body["route"]["start_label"] == "Fresh Market"
    assert body["items"][0]["sku"] == upstairs.sku and body["items"][0]["floor"] == 2
    assert body["route"]["floor_changes"] >= 1
    assert {seg["floor"] for seg in body["route"]["segments"]} == {1, 2}
    step_free = client.post("/stores/riverside/search", json={"text": upstairs.name, "step_free": True}).json()
    kinds = [(s["kind"], s["icon"]) for s in step_free["route"]["steps"]]
    assert ("take_connector", "elevator") in kinds and step_free["route"]["accessible_only"] is True


def test_search_start_point_field(client):
    body = client.post("/stores/central/search", json={"text": BAGELS, "start": "Produce"}).json()
    assert body["route"]["start_label"] == "Produce"


def test_search_out_of_stock_item(client):
    body = client.post("/stores/central/search", json={"text": "ArtBox Watercolour Paints 12 pack"}).json()
    item = body["items"][0]
    assert (item["status"], item["stock_status"], item["in_stock"]) == ("unavailable", "out_of_stock", 0)
    assert body["route"] is None


def test_search_limits(client):
    settings = load_settings()
    _error(client.post("/stores/central/search", json={"text": "a" * (settings.max_query_chars + 1)}), 422, "TEXT_TOO_LONG")
    _error(client.post("/stores/central/search", json={"text": ""}), 422, "VALIDATION_ERROR")
    _error(client.post("/stores/central/search", json={}), 422, "VALIDATION_ERROR")
    _error(client.post("/stores/central/search", content=b"{not json", headers={"Content-Type": "application/json"}),
           422, "VALIDATION_ERROR")
    long_list = ", ".join(["milk"] * (settings.max_items + 3))
    ok = client.post("/stores/central/search", json={"text": long_list[: settings.max_query_chars]})
    assert ok.status_code == 200


# ---------- basket ----------


@pytest.mark.parametrize("store", STORES)
def test_basket_route_matches_typed_search(client, datasets, store):
    ds = datasets[store]
    a, b = _single_place(ds, 1), _single_place(ds, 2)
    basket = client.post(f"/stores/{store}/basket/route",
                         json={"items": [{"sku": a.sku, "qty": 2}, {"sku": b.sku, "qty": 1}]})
    assert basket.status_code == 200
    body = basket.json()
    assert body["status"] == "ok"
    assert [(i["sku"], i["quantity_requested"]) for i in body["items"]] == [(a.sku, 2), (b.sku, 1)]
    typed = client.post(f"/stores/{store}/search", json={"text": f"{a.name} and {b.name}"}).json()
    assert body["route"]["path"] == typed["route"]["path"]
    assert body["route"]["total_distance_m"] == typed["route"]["total_distance_m"]


def test_basket_limits_and_unknown_sku(client, datasets):
    settings = load_settings()
    skus = [p.sku for p in datasets["central"].products]
    _error(client.post("/stores/central/basket/route", json={"items": []}), 422, "VALIDATION_ERROR")
    _error(client.post("/stores/central/basket/route",
                       json={"items": [{"sku": s, "qty": 1} for s in skus[: settings.max_items + 1]]}),
           422, "TOO_MANY_ITEMS")
    for qty in (settings.basket_min_quantity - 1, settings.basket_max_quantity + 1):
        _error(client.post("/stores/central/basket/route", json={"items": [{"sku": skus[0], "qty": qty}]}),
               422, "QUANTITY_OUT_OF_RANGE")
    _error(client.post("/stores/central/basket/route", json={"items": [{"sku": skus[0], "qty": 1}, {"sku": skus[0], "qty": 2}]}),
           422, "DUPLICATE_SKU")
    _error(client.post("/stores/central/basket/route", json={"items": [{"sku": "NOPE-1", "qty": 1}]}),
           404, "PRODUCT_NOT_FOUND")


# ---------- map ----------


@pytest.mark.parametrize("store", STORES)
def test_map(client, datasets, store):
    ds = datasets[store]
    body = client.get(f"/stores/{store}/map").json()
    assert body["store_id"] == store and body["floors"] == ds.graph.floors
    assert body["bounds"] == {"width": ds.graph.bounds.width, "height": ds.graph.bounds.height}
    assert [n["id"] for n in body["nodes"]] == [n.id for n in ds.graph.nodes]
    nodes = {n.id: n for n in ds.graph.nodes}
    assert len(body["edges"]) == len(ds.graph.edges)
    assert all(e["floor"] == nodes[e["a"]].floor for e in body["edges"])
    assert {(c["type"], c["accessible"]) for c in body["connectors"]} == {(c.type.value, c.accessible) for c in ds.graph.connectors}
    assert {z["label"] for z in body["zones"]} == {n.label for n in ds.graph.nodes if n.type.value in ("zone_front", "aisle", "checkout", "entrance")}


# ---------- unknown store everywhere ----------


@pytest.mark.parametrize(
    "method, path, payload",
    [
        ("get", "/stores/nope/categories", None),
        ("get", "/stores/nope/products", None),
        ("get", "/stores/nope/suggest?q=milk", None),
        ("post", "/stores/nope/search", {"text": "milk"}),
        ("post", "/stores/nope/clarify", {"session_id": "x", "item_index": 0, "sku": "X"}),
        ("get", "/stores/nope/products/BAK-BAG-009", None),
        ("post", "/stores/nope/basket/route", {"items": [{"sku": "BAK-BAG-009", "qty": 1}]}),
        ("get", "/stores/nope/map", None),
        ("get", "/stores/nope/products/BAK-BAG-009/image", None),
    ],
)
def test_unknown_store_id(client, method, path, payload):
    resp = getattr(client, method)(path, json=payload) if payload is not None else getattr(client, method)(path)
    _error(resp, 404, "STORE_NOT_FOUND")


def test_unknown_route_and_method(client):
    _error(client.get("/nowhere"), 404, "NOT_FOUND")
    _error(client.delete("/stores"), 405, "METHOD_NOT_ALLOWED")


# ---------- prices optional ----------


def test_store_without_prices_returns_null_price(tmp_path):
    folder = tmp_path / "s"
    folder.mkdir()
    for f in STORE_FILES:
        shutil.copy(ROOT / "data" / "store_riverside" / f, folder / f)
    (folder / "images").mkdir()
    reg = tmp_path / "stores.json"
    reg.write_text(json.dumps({"stores": [{"id": "plain", "name": "Plain", "data_dir": str(folder)}]}), encoding="utf-8")
    provider = LocalFilesProvider(reg)
    sku = provider.load_dataset("plain").products[0].sku
    Image.new("RGB", (30, 30), "red").save(folder / "images" / f"{sku}.png")
    with TestClient(create_app(provider=provider)) as c:
        assert c.get("/stores").json()[0]["has_prices"] is False
        assert c.get(f"/stores/plain/products/{sku}").json()["price"] is None
        assert all(p["price"] is None for p in c.get("/stores/plain/products").json()["items"])
        img = c.get(f"/stores/plain/products/{sku}/image")
        assert img.headers["content-type"] == "image/png"


# ---------- middleware: request ids, logging, rate limit, CORS ----------


def test_request_id_echoed_or_generated(client):
    assert client.get("/health", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"] == "abc-123"
    generated = client.get("/health", headers={"X-Request-ID": "bad id <script>"}).headers["X-Request-ID"]
    assert generated != "bad id <script>" and len(generated) == 32


def test_logs_have_request_id_but_no_body_text_or_secrets(client, caplog):
    caplog.set_level(logging.INFO, logger="planogram_api")
    secret_text = "ZEBRA-SECRET-SHOPPER-TEXT"
    resp = client.post("/stores/central/search", json={"text": secret_text},
                       headers={"Authorization": "Bearer sk-live-very-secret", "X-Request-ID": "log-check-1"})
    assert resp.status_code == 200
    client.get("/stores/central/suggest", params={"q": "QUERY-SECRET-TEXT"})
    logged = caplog.text
    assert "log-check-1" in logged and "/stores/{store_id}/search" in logged
    for leak in (secret_text, "sk-live-very-secret", "Bearer", "QUERY-SECRET-TEXT"):
        assert leak not in logged


def _limited_app(limit: int):
    settings = load_settings().model_copy(update={"api_rate_limit_per_minute": limit})
    return TestClient(create_app(settings=settings))


def test_rate_limit(monkeypatch):
    monkeypatch.delenv("PLANOGRAM_TRUST_PROXY", raising=False)
    with _limited_app(3) as c:
        for _ in range(3):
            assert c.get("/stores").status_code == 200
        err = _error(c.get("/stores"), 429, "RATE_LIMITED")
        assert "minute" in err["message"]
        assert int(c.get("/stores").headers["Retry-After"]) >= 1
        assert c.get("/health").status_code == 200  # health checks are not limited
        # without trust-proxy, a forwarded address does not get a fresh allowance
        assert c.get("/stores", headers={"X-Forwarded-For": "10.0.0.9"}).status_code == 429


def test_rate_limit_trusts_forwarded_for_only_when_enabled(monkeypatch):
    monkeypatch.setenv("PLANOGRAM_TRUST_PROXY", "1")
    with _limited_app(2) as c:
        for ip in ("10.0.0.1", "10.0.0.2"):
            assert c.get("/stores", headers={"X-Forwarded-For": ip}).status_code == 200
            assert c.get("/stores", headers={"X-Forwarded-For": ip}).status_code == 200
            assert c.get("/stores", headers={"X-Forwarded-For": ip}).status_code == 429


def test_cors_from_environment(monkeypatch):
    monkeypatch.setenv("PLANOGRAM_CORS_ORIGINS", "https://shop.example, https://admin.example")
    with TestClient(create_app()) as c:
        pre = c.options("/stores", headers={"Origin": "https://shop.example", "Access-Control-Request-Method": "GET"})
        assert pre.headers.get("access-control-allow-origin") == "https://shop.example"
        other = c.get("/stores", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in other.headers


def test_no_cors_when_not_configured(monkeypatch):
    monkeypatch.delenv("PLANOGRAM_CORS_ORIGINS", raising=False)
    with TestClient(create_app()) as c:
        assert "access-control-allow-origin" not in c.get("/stores", headers={"Origin": "https://shop.example"}).headers


# ---------- engines cached per store, one lock each ----------


def test_engine_built_once_per_store(client):
    engines = client.app.state.engines
    a = engines.get("central")
    assert engines.get("central") is a
    assert engines.get("riverside") is not a
    assert a.lock is not engines.get("riverside").lock
