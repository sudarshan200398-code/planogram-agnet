"""Basket: add, edit, remove, clear, limits, and routing through the same pipeline as typed text."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from planogram_agent.basket import (
    EMPTY_BASKET_MESSAGE,
    add_item,
    basket_finder_for,
    basket_text,
    clamp_quantity,
    clear_basket,
    plan_basket,
    remove_item,
    set_quantity,
)
from planogram_agent.interface import create_finder, run_query
from planogram_agent.llm.fake_client import FakeLLMClient
from planogram_agent.llm.no_model import NoModelClient
from planogram_agent.runtime.orchestrator import Orchestrator
from planogram_agent.schemas import NodeType
from planogram_agent.settings import Settings, load_settings
from planogram_agent.tools import check_inventory, get_location

APP_FILE = str(Path(__file__).resolve().parent.parent / "src" / "planogram_agent" / "ui" / "streamlit_app.py")
STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"


@pytest.fixture(scope="module")
def finder():
    return create_finder(STORE_DIR, settings=load_settings(), client=NoModelClient())


@pytest.fixture(scope="module")
def settings(finder):
    return finder.settings


def _plain_name(name: str) -> bool:
    """Names a shopper can join with ', ' and ' and ' without the list itself being ambiguous."""
    low = f" {name.lower()} "
    return "," not in name and "&" not in name and " and " not in low


def _products_on_floor(dataset, floor: int, stock: str = "available") -> list:
    """Products whose every shelf placement is on one floor, with the given stock status."""
    found = []
    for p in sorted(dataset.products, key=lambda p: p.sku):
        locs = get_location(p.sku, dataset)
        if locs and {l.floor for l in locs} == {floor} and check_inventory(p.sku, dataset) == stock and _plain_name(p.name):
            found.append(p)
    return found


def _floors(dataset) -> list[int]:
    return sorted({n.floor for n in dataset.graph.nodes})


def _picks(dataset, count: int) -> list:
    """`count` in-stock products spread over the lowest and highest floor, the far floor first."""
    floors = _floors(dataset)
    low, high = _products_on_floor(dataset, floors[0]), _products_on_floor(dataset, floors[-1])
    order = [high[0], low[0], high[11], low[23], low[47]]
    return order[:count]


def _typed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _basket_of(products, settings, qty: dict[str, int] | None = None) -> dict:
    basket: dict = {}
    for p in products:
        assert add_item(basket, p.sku, p.name, settings).ok
        if qty and p.sku in qty:
            set_quantity(basket, p.sku, qty[p.sku], settings)
    return basket


# ---------- config ----------


def test_basket_quantity_limits_live_in_config(settings):
    assert settings.basket_min_quantity == 1
    assert settings.basket_max_quantity == 99
    assert Settings().basket_max_quantity == 99


# ---------- add, edit, remove, clear ----------


def test_add_new_item(settings):
    basket: dict = {}
    result = add_item(basket, "SKU-1", "Some Product 1 kg", settings)
    assert result.ok
    assert basket == {"SKU-1": {"name": "Some Product 1 kg", "qty": 1}}


def test_add_same_item_again_adds_one(settings):
    basket: dict = {}
    add_item(basket, "SKU-1", "Some Product", settings)
    assert add_item(basket, "SKU-1", "Some Product", settings).ok
    assert basket["SKU-1"]["qty"] == 2
    assert len(basket) == 1


def test_add_again_stops_at_max_quantity(settings):
    basket: dict = {}
    add_item(basket, "SKU-1", "Some Product", settings)
    set_quantity(basket, "SKU-1", settings.basket_max_quantity, settings)
    result = add_item(basket, "SKU-1", "Some Product", settings)
    assert basket["SKU-1"]["qty"] == settings.basket_max_quantity
    assert str(settings.basket_max_quantity) in result.message


def test_edit_quantity(settings):
    basket: dict = {}
    add_item(basket, "SKU-1", "Some Product", settings)
    assert set_quantity(basket, "SKU-1", 7, settings) == 7
    assert basket["SKU-1"]["qty"] == 7


@pytest.mark.parametrize("given, kept", [(0, 1), (-5, 1), (1, 1), (42, 42), (99, 99), (100, 99), (250, 99)])
def test_quantity_is_clamped_to_1_to_99(settings, given, kept):
    assert clamp_quantity(given, settings) == kept
    basket: dict = {}
    add_item(basket, "SKU-1", "Some Product", settings)
    assert set_quantity(basket, "SKU-1", given, settings) == kept
    assert basket["SKU-1"]["qty"] == kept


def test_edit_quantity_of_missing_item_does_nothing(settings):
    basket: dict = {}
    assert set_quantity(basket, "NOPE", 3, settings) is None
    assert basket == {}


def test_remove_item(settings):
    basket: dict = {}
    add_item(basket, "SKU-1", "A", settings)
    add_item(basket, "SKU-2", "B", settings)
    remove_item(basket, "SKU-1")
    assert list(basket) == ["SKU-2"]
    remove_item(basket, "NOPE")  # removing something absent is not an error
    assert list(basket) == ["SKU-2"]


def test_clear_basket(settings):
    basket: dict = {}
    add_item(basket, "SKU-1", "A", settings)
    add_item(basket, "SKU-2", "B", settings)
    clear_basket(basket)
    assert basket == {}


# ---------- limits ----------


def test_add_over_max_items_is_refused(settings):
    small = settings.model_copy(update={"max_items": 2})
    basket: dict = {}
    assert add_item(basket, "SKU-1", "A", small).ok
    assert add_item(basket, "SKU-2", "B", small).ok
    result = add_item(basket, "SKU-3", "C", small)
    assert not result.ok
    assert "2" in result.message
    assert list(basket) == ["SKU-1", "SKU-2"]
    assert add_item(basket, "SKU-1", "A", small).ok  # more of an item already there is still fine
    assert basket["SKU-1"]["qty"] == 2


def test_add_over_max_query_chars_is_refused(settings):
    first, second = "Alpha Product 400 g", "Beta Product 400 g"
    tight = settings.model_copy(update={"max_query_chars": len(f"{first} x {settings.basket_max_quantity}")})
    basket: dict = {}
    assert add_item(basket, "SKU-1", first, tight).ok
    result = add_item(basket, "SKU-2", second, tight)
    assert not result.ok
    assert str(tight.max_query_chars) in result.message
    assert list(basket) == ["SKU-1"]


def test_full_basket_at_max_quantity_still_fits_query_limit(finder, settings):
    """Any basket the add rules allow stays within max_query_chars, whatever the quantities."""
    basket: dict = {}
    for p in sorted(finder.dataset.products, key=lambda p: -len(p.name)):
        if not add_item(basket, p.sku, p.name, settings).ok:
            break
    assert basket
    for sku in basket:
        set_quantity(basket, sku, settings.basket_max_quantity, settings)
    assert len(basket_text(basket)) <= settings.max_query_chars


# ---------- text ----------


def test_basket_text_uses_exact_names_and_quantities(settings):
    basket: dict = {}
    add_item(basket, "SKU-1", "Urban Thread Canvas Sneakers UK 6", settings)
    add_item(basket, "SKU-2", "Daily Bake White Sandwich Bread 400 g", settings)
    set_quantity(basket, "SKU-2", 3, settings)
    assert basket_text(basket) == "Urban Thread Canvas Sneakers UK 6\nDaily Bake White Sandwich Bread 400 g x 3"
    assert basket_text({}) == ""


# ---------- pipeline ----------


def test_empty_basket_returns_none_with_clear_message(finder):
    assert plan_basket(finder, {}) is None
    assert "empty" in EMPTY_BASKET_MESSAGE.lower()


def _route_view(answer):
    r = answer.route
    assert r is not None
    return (r.start_node, r.ordered_skus, r.path, r.walking_distance, r.floor_changes, r.directions_text)


@pytest.mark.parametrize("count", [1, 2, 5])
def test_basket_route_equals_typed_list_route(finder, settings, count):
    products = _picks(finder.dataset, count)
    qty = {products[0].sku: 3}
    basket = _basket_of(products, settings, qty)

    from_basket = plan_basket(finder, basket)
    typed = run_query(finder, _typed([p.name for p in products]))

    assert from_basket.status == typed.status == "ok"
    assert from_basket.verified and typed.verified
    assert _route_view(from_basket) == _route_view(typed)
    assert [(it.sku, it.name, it.requested, it.qty) for it in from_basket.items] == [
        (p.sku, p.name, p.name, qty.get(p.sku, 1)) for p in products
    ]
    floors = {loc.floor for p in products for loc in get_location(p.sku, finder.dataset)}
    if count > 1:
        assert len(floors) >= 2
    assert from_basket.route.floor_changes >= 1  # every case reaches the far floor


def test_basket_route_follows_start_and_step_free(finder, settings):
    products = _picks(finder.dataset, 2)
    basket = _basket_of(products, settings)
    names = [p.name for p in products]
    start = next(n for n in finder.dataset.graph.nodes if n.type != NodeType.JUNCTION and n.floor == _floors(finder.dataset)[-1])
    kwargs = {"start": start.label, "floor": start.floor, "accessible_only": True}
    assert _route_view(plan_basket(finder, basket, **kwargs)) == _route_view(run_query(finder, _typed(names), **kwargs))


def test_out_of_stock_item_is_reported_and_not_routed(finder, settings):
    floors = _floors(finder.dataset)
    in_stock = _products_on_floor(finder.dataset, floors[0])[0]
    out = next(p for f in floors for p in _products_on_floor(finder.dataset, f, stock="unavailable"))
    basket = _basket_of([in_stock, out], settings)

    from_basket = plan_basket(finder, basket)
    typed = run_query(finder, _typed([in_stock.name, out.name]))

    by_sku = {it.sku: it for it in from_basket.items}
    assert by_sku[out.sku].status == "unavailable"
    assert by_sku[in_stock.sku].status == "available"
    assert out.sku not in from_basket.route.ordered_skus
    assert from_basket.status == typed.status
    assert [(it.sku, it.status) for it in from_basket.items] == [(it.sku, it.status) for it in typed.items]
    assert _route_view(from_basket) == _route_view(typed)


def test_basket_never_calls_the_ai_model(settings):
    model = FakeLLMClient(["{}"] * 5)
    finder_with_model = Orchestrator(dataset=create_finder(STORE_DIR, client=NoModelClient()).dataset,
                                     settings=settings, client=model)
    products = _picks(finder_with_model.dataset, 2)
    answer = plan_basket(finder_with_model, _basket_of(products, settings))
    assert model.calls == []
    assert answer.status == "ok" and answer.verified


def test_basket_finder_is_shared_and_model_free(finder):
    bf = basket_finder_for(finder)
    assert bf is basket_finder_for(finder)
    assert isinstance(bf.client, NoModelClient)
    assert bf.dataset is finder.dataset and bf.settings is finder.settings


# ---------- page ----------


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("PLANOGRAM_PROVIDER", "none")
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def _basket(at: AppTest) -> dict:
    return dict(at.session_state["basket"])


def _add_buttons(at: AppTest, prefix: str) -> list:
    return [b for b in at.button if b.key and b.key.startswith(prefix)]


def test_new_session_starts_with_empty_basket(app):
    assert _basket(app) == {}
    assert any("empty" in c.value.lower() for c in app.sidebar.caption)


def test_plan_empty_basket_shows_message_not_error(app):
    app.button(key="basket_plan").click().run()
    assert not app.exception
    assert not app.error
    assert any(EMPTY_BASKET_MESSAGE == i.value for i in app.info)
    assert app.session_state["last_answer"] is None


def test_add_from_answer_edit_remove_clear(app):
    app.button[0].click().run()  # Example: Multi-product
    adds = _add_buttons(app, "add_item_")
    found = [it for it in app.session_state["last_answer"].items if it.sku]
    assert len(adds) == len(found) == 2

    adds[0].click().run()
    sku0 = found[0].sku
    assert _basket(app) == {sku0: {"name": found[0].name, "qty": 1}}
    assert any(found[0].name in m.value for m in app.sidebar.markdown)

    app.number_input(key=f"basket_qty_{sku0}").set_value(5).run()
    assert _basket(app)[sku0]["qty"] == 5

    app.button(key=f"basket_remove_{sku0}").click().run()
    assert _basket(app) == {}

    for b in _add_buttons(app, "add_item_"):
        b.click().run()
    assert len(_basket(app)) == 2
    app.button(key="basket_clear").click().run()
    assert _basket(app) == {}
    assert not app.exception


def test_plan_route_for_basket_matches_typed_answer(app):
    app.button[0].click().run()  # Example: Multi-product
    typed_route = app.session_state["last_answer"].route
    for b in _add_buttons(app, "add_item_"):
        b.click().run()
    app.button(key="basket_plan").click().run()
    assert not app.exception
    planned = app.session_state["last_answer"]
    assert planned.route.ordered_skus == typed_route.ordered_skus
    assert planned.route.path == typed_route.path
    assert any(s.value == "Route" for s in app.subheader)


def test_out_of_stock_answer_item_can_be_added_and_is_reported(app):
    app.button[2].click().run()  # Example: Out-of-stock
    item = app.session_state["last_answer"].items[0]
    assert item.status == "unavailable"
    app.button(key=f"add_item_{item.index}_{item.sku}").click().run()
    assert item.sku in _basket(app)
    app.button(key="basket_plan").click().run()
    assert not app.exception
    assert app.session_state["last_answer"].items[0].status == "unavailable"


def test_fallback_has_add_button_per_suggestion_row(monkeypatch):
    monkeypatch.setenv("PLANOGRAM_PROVIDER", "none")
    monkeypatch.setitem(sys.modules, "streamlit_searchbox", None)
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    next(t for t in at.text_input if t.label == "Find a product").input("bre").run()
    rows = [b for b in at.button if b.key and b.key.startswith("suggest_")]
    adds = _add_buttons(at, "add_suggest_")
    assert len(adds) == len(rows) > 0
    sku = adds[0].key.removeprefix("add_suggest_")
    adds[0].click().run()
    assert not at.exception
    assert list(_basket(at)) == [sku]
    assert _basket(at)[sku]["name"] == rows[0].label.split(" | ")[0]


def test_picked_dropdown_product_has_add_button(monkeypatch):
    streamlit_searchbox = pytest.importorskip("streamlit_searchbox")
    finder = create_finder(STORE_DIR, client=NoModelClient())
    product = _picks(finder.dataset, 1)[0]
    monkeypatch.setenv("PLANOGRAM_PROVIDER", "none")
    monkeypatch.setattr(streamlit_searchbox, "st_searchbox", lambda *a, **k: product.sku)
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    assert at.text_area[0].value == product.name  # the pick still fills the query box
    at.button(key="add_picked").click().run()
    assert not at.exception
    assert _basket(at) == {product.sku: {"name": product.name, "qty": 1}}
