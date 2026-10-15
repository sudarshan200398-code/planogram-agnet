"""One search bar: Search-for row first, product rows after; picks; fallback; basket on the main page."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from planogram_agent.autocomplete import suggest
from planogram_agent.interface import create_finder
from planogram_agent.llm.no_model import NoModelClient
from planogram_agent.ui.present import search_options

APP_FILE = str(Path(__file__).resolve().parent.parent / "src" / "planogram_agent" / "ui" / "streamlit_app.py")
STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"
SENTENCE = "im near produce and i want milk"
BAGELS = "Daily Bake Plain Bagels 4 pack"
SEARCH_TEXTS = [
    SENTENCE,
    "2 x Daily Bake Plain Bagels 4 pack, Store Brand Shredded Cheddar 400 g",
    "I am near produce and I want Daily Bake Plain Bagels 4 pack",
]


@pytest.fixture(scope="module")
def finder():
    return create_finder(STORE_DIR, client=NoModelClient())


# ---------- dropdown rows ----------


def test_short_prefix_gives_search_row_first_then_products(finder):
    rows = search_options("mi", finder.dataset, finder.settings)
    products = suggest("mi", finder.dataset, finder.settings)
    assert products
    assert rows[0] == ('Search for "mi"', ("search", "mi"))
    assert rows[1:] == [(s.label, ("product", s.sku)) for s in products]


def test_sentence_gives_only_the_search_row(finder):
    assert search_options(SENTENCE, finder.dataset, finder.settings) == [
        (f'Search for "{SENTENCE}"', ("search", SENTENCE))
    ]


@pytest.mark.parametrize("text", ["", "   ", None])
def test_empty_text_gives_no_rows(finder, text):
    assert search_options(text, finder.dataset, finder.settings) == []


def test_search_row_uses_trimmed_text(finder):
    assert search_options("  milk  ", finder.dataset, finder.settings)[0] == ('Search for "milk"', ("search", "milk"))


# ---------- page helpers ----------


def _fake_searchbox(monkeypatch, picks: list):
    """Replace the add-on with one that reports each queued pick once through submit_function."""
    streamlit_searchbox = pytest.importorskip("streamlit_searchbox")

    def fake(search_function, *args, submit_function=None, **kwargs):
        if picks:
            submit_function(picks.pop(0))
        return None

    monkeypatch.setattr(streamlit_searchbox, "st_searchbox", fake)


def _app(monkeypatch) -> AppTest:
    monkeypatch.setenv("PLANOGRAM_PROVIDER", "none")
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def _find_via_paste_box(monkeypatch, text: str):
    at = _app(monkeypatch)
    at.text_area[0].input(text)
    at.button(key="find").click().run()
    assert not at.exception
    return at.session_state["last_answer"]


def _view(ans):
    route = ans.route
    return (
        ans.status,
        [(it.requested, it.sku, it.status, it.qty, it.quantity) for it in ans.items],
        (route.start_label, route.ordered_skus, route.path, route.walking_distance) if route else None,
        [o.sku for o in ans.question.options] if ans.question else None,
    )


# ---------- picks ----------


def test_picking_a_product_runs_its_search_and_adds_nothing(monkeypatch, finder):
    sku = next(p.sku for p in finder.dataset.products if p.name == BAGELS)
    _fake_searchbox(monkeypatch, [("product", sku)])
    at = _app(monkeypatch)
    ans = at.session_state["last_answer"]
    assert ans is not None and ans.status == "ok"
    assert [(it.sku, it.name, it.requested) for it in ans.items] == [(sku, BAGELS, BAGELS)]
    assert at.session_state["basket"] == {}
    assert any(BAGELS in m.value for m in at.markdown)


@pytest.mark.parametrize("text", SEARCH_TEXTS)
def test_search_row_matches_the_paste_box_find(monkeypatch, text):
    expected = _view(_find_via_paste_box(monkeypatch, text))
    _fake_searchbox(monkeypatch, [("search", text)])
    at = _app(monkeypatch)
    assert _view(at.session_state["last_answer"]) == expected


class _RealisticComponent:
    """Stands in for the add-on's browser part only. Like the real one, the last value it sent is
    returned again on every rerun until the component is remounted under a new key."""

    def __init__(self):
        self.values: dict[str, dict] = {}
        self.current_key = ""

    def __call__(self, **kwargs):
        self.current_key = kwargs["key"]
        return self.values.get(self.current_key)

    def send(self, interaction: str, value):
        self.values[self.current_key] = {"interaction": interaction, "value": value}


@pytest.fixture
def real_addon(monkeypatch):
    """The pinned add-on's own Python code with a realistic component, plus a run_query call log."""
    streamlit_searchbox = pytest.importorskip("streamlit_searchbox")
    import planogram_agent.interface as interface

    component = _RealisticComponent()
    monkeypatch.setattr(streamlit_searchbox, "_get_react_component", component)
    calls: list[str] = []
    real = interface.run_query
    monkeypatch.setattr(interface, "run_query", lambda f, text, **kw: calls.append(text) or real(f, text, **kw))
    return component, calls


def _type_and_pick(at: AppTest, component: _RealisticComponent, text: str, row) -> None:
    component.send("search", text)
    at.run()
    options = at.session_state["product_searchbox"]["options_py"]
    component.send("submit", options.index(row))
    at.run()
    assert not at.exception


def test_same_row_can_be_picked_twice_with_the_real_addon(monkeypatch, finder, real_addon):
    """Fails if clearing the add-on's stored result stops working (add-on pinned at 0.1.24)."""
    component, calls = real_addon
    sku = next(p.sku for p in finder.dataset.products if p.name == BAGELS)
    at = _app(monkeypatch)
    for _ in range(2):
        _type_and_pick(at, component, BAGELS, ("product", sku))
    assert calls == [BAGELS, BAGELS]
    assert at.session_state["product_searchbox"]["result"] is None


def test_a_pick_is_not_repeated_by_later_reruns(monkeypatch, real_addon):
    """After Search for..., choosing a clarification option must keep the chosen answer."""
    component, calls = real_addon
    at = _app(monkeypatch)
    _type_and_pick(at, component, SENTENCE, ("search", SENTENCE))
    assert at.session_state["last_answer"].status == "needs_clarification"
    next(b for b in at.button if b.key and b.key.startswith("opt_")).click().run()
    assert not at.exception
    assert at.session_state["last_answer"].status != "needs_clarification"
    at.run()  # any later rerun, e.g. an Add to basket click
    assert at.session_state["last_answer"].status != "needs_clarification"
    assert calls == [SENTENCE]


# ---------- fallback ----------


@pytest.fixture
def fallback(monkeypatch):
    monkeypatch.setitem(sys.modules, "streamlit_searchbox", None)
    return _app(monkeypatch)


def test_fallback_find_runs_the_full_pipeline(monkeypatch, fallback):
    fallback.text_input(key="product_search_text").input(SENTENCE).run()
    fallback.button(key="find_text").click().run()
    assert not fallback.exception
    got = _view(fallback.session_state["last_answer"])
    monkeypatch.delitem(sys.modules, "streamlit_searchbox")
    assert got == _view(_find_via_paste_box(monkeypatch, SENTENCE))


def test_fallback_rows_and_add(fallback):
    fallback.text_input(key="product_search_text").input("bre").run()
    rows = [b for b in fallback.button if b.key and b.key.startswith("suggest_")]
    adds = [b for b in fallback.button if b.key and b.key.startswith("add_suggest_")]
    assert rows and len(adds) == len(rows)
    adds[0].click().run()
    assert list(fallback.session_state["basket"]) == [adds[0].key.removeprefix("add_suggest_")]


# ---------- basket on the main page ----------


def test_add_to_basket_on_card_fills_basket_and_confirms(monkeypatch):
    at = _app(monkeypatch)
    at.text_area[0].input(BAGELS)
    at.button(key="find").click().run()
    item = at.session_state["last_answer"].items[0]
    at.button(key=f"add_item_{item.index}_{item.sku}").click().run()
    assert not at.exception
    assert at.session_state["basket"] == {item.sku: {"name": BAGELS, "qty": 1}}
    assert any(c.value == f"Added: {BAGELS}" for c in at.caption)


def test_basket_is_on_the_main_page_and_sidebar_only_has_settings(monkeypatch):
    at = _app(monkeypatch)
    assert any(s.value == "Your basket" for s in at.main.subheader)
    assert at.button(key="basket_plan").label == "Find route for basket"
    assert len(at.sidebar.button) == 0
    assert [e.label for e in at.sidebar.expander] == ["Store and model"]
    assert not any(b.key == "add_picked" for b in at.button)
