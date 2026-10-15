"""Autocomplete suggestions: deterministic, built on the product matcher and the store data."""
from __future__ import annotations

import string
import sys
from collections import Counter
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from planogram_agent.autocomplete import Suggestion, suggest
from planogram_agent.data_loader import load_dataset
from planogram_agent.interface import create_finder
from planogram_agent.llm.no_model import NoModelClient
from planogram_agent.matching import get_search_index
from planogram_agent.settings import Settings, load_settings
from planogram_agent.tools import check_inventory, get_location

APP_FILE = str(Path(__file__).resolve().parent.parent / "src" / "planogram_agent" / "ui" / "streamlit_app.py")
STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(STORE_DIR, validate=True)


@pytest.fixture(scope="module")
def settings():
    return load_settings()


def _is_bread(dataset, sku: str) -> bool:
    p = next(p for p in dataset.products if p.sku == sku)
    return "bread" in p.name.lower() or any("bread" in k.lower() for k in p.keywords)


# ---------- config ----------


def test_autocomplete_limits_live_in_config(settings):
    assert settings.autocomplete_limit == 8
    assert settings.autocomplete_min_chars == 2
    assert Settings().autocomplete_limit == 8


# ---------- prefix ----------


def test_prefix_bre_returns_breads_only(dataset, settings):
    result = suggest("bre", dataset, settings)
    assert len(result) == settings.autocomplete_limit
    assert all(isinstance(s, Suggestion) for s in result)
    assert all(_is_bread(dataset, s.sku) for s in result), [s.name for s in result]


def test_prefix_is_case_and_space_insensitive(dataset, settings):
    assert [s.sku for s in suggest("  BRE ", dataset, settings)] == [s.sku for s in suggest("bre", dataset, settings)]


def test_multi_word_prefix_narrows_by_earlier_words(dataset, settings):
    result = suggest("golden crust bre", dataset, settings)
    assert result
    assert all(_is_bread(dataset, s.sku) and s.name.startswith("Golden Crust") for s in result)


def test_full_name_puts_that_product_first(dataset, settings):
    result = suggest("Daily Bake White Sandwich Bread 400 g", dataset, settings)
    assert result[0].name == "Daily Bake White Sandwich Bread 400 g"


# ---------- typos ----------


@pytest.mark.parametrize("typo", ["braed", "bred"])
def test_typo_still_suggests_breads(dataset, settings, typo):
    result = suggest(typo, dataset, settings)
    assert result
    assert all(_is_bread(dataset, s.sku) for s in result), [s.name for s in result]


def test_swapped_letters_mlik_suggests_milk(dataset, settings):
    result = suggest("mlik", dataset, settings)
    assert result
    assert all("milk" in s.name.lower() for s in result), [s.name for s in result]


# ---------- too short / nothing ----------


@pytest.mark.parametrize("text", ["", " ", "b", "B ", "  x  ", "1", "!!"])
def test_empty_or_one_letter_returns_nothing(dataset, settings, text):
    assert suggest(text, dataset, settings) == []


def test_gibberish_returns_nothing(dataset, settings):
    assert suggest("zzqx", dataset, settings) == []


# ---------- shown data ----------


def test_out_of_stock_is_shown_and_marked(dataset, settings):
    result = suggest("artbox water", dataset, settings)
    paints = next((s for s in result if s.sku == "TOY-ART-005"), None)
    assert paints is not None, [s.name for s in result]
    assert check_inventory("TOY-ART-005", dataset) == "unavailable"
    assert paints.stock == "out_of_stock"
    assert "Out of stock" in paints.label


def test_label_has_name_floor_zone_and_stock(dataset, settings):
    for s in suggest("bre", dataset, settings):
        locs = get_location(s.sku, dataset)
        assert s.label.startswith(s.name)
        for loc in locs:
            assert f"Level {loc.floor}, {loc.zone}" in s.label
        expected_stock = {"available": "In stock", "unavailable": "Out of stock", "unknown": "Stock unknown"}
        assert expected_stock[check_inventory(s.sku, dataset)] in s.label


@pytest.mark.parametrize("prefix", ["br", "ch", "mi", "sh"])
def test_most_common_word_comes_first(dataset, settings, prefix):
    """Completions shared by more products rank higher; ties broken alphabetically."""
    indexed = get_search_index(dataset).indexed
    counts = Counter(w for p in indexed for w in set(p.all_words) if w.startswith(prefix))
    assert prefix not in counts  # an exact word would rank first regardless of count
    order = sorted(counts, key=lambda w: (-counts[w], w))
    words_of = {p.sku: set(p.all_words) for p in indexed}

    result = suggest(prefix, dataset, settings)
    ranks = [min(order.index(w) for w in words_of[s.sku] if w in counts) for s in result]
    assert result and ranks[0] == 0, [s.name for s in result]
    assert ranks == sorted(ranks), list(zip(ranks, [s.name for s in result]))


def test_suggestions_are_sorted_best_first(dataset, settings):
    result = suggest("milk", dataset, settings)
    scores = [s.score for s in result]
    assert scores == sorted(scores, reverse=True)


# ---------- cap ----------


def test_list_never_exceeds_cap(dataset, settings):
    prefixes = {"br", "ch", "mi", "st", "da", "co", "gi", "sh", "milk", "store", "store brand", "daily bake"}
    prefixes.update(a + b for a in "bcdmst" for b in "aeiloru")
    for p in sorted(prefixes):
        assert len(suggest(p, dataset, settings)) <= settings.autocomplete_limit, p


def test_cap_follows_config(dataset, settings):
    small = settings.model_copy(update={"autocomplete_limit": 3})
    assert len(suggest("bre", dataset, small)) == 3


@pytest.mark.slow
def test_cap_holds_for_every_two_letter_prefix(dataset, settings):
    for a in string.ascii_lowercase:
        for b in string.ascii_lowercase:
            assert len(suggest(a + b, dataset, settings)) <= settings.autocomplete_limit, a + b


# ---------- model off, no network ----------


def test_works_with_model_off_and_no_network(monkeypatch):
    import socket

    monkeypatch.setenv("PLANOGRAM_PROVIDER", "none")
    finder = create_finder(STORE_DIR)
    assert isinstance(finder.client, NoModelClient)
    with pytest.raises(RuntimeError, match="network access is not allowed"):
        socket.create_connection(("203.0.113.1", 80), timeout=1.0)
    result = suggest("bre", finder.dataset, finder.settings)
    assert len(result) == finder.settings.autocomplete_limit


# ---------- page ----------


def _query_box_value(at: AppTest) -> str:
    return at.text_area[0].value


def test_page_renders_search_box_without_errors(monkeypatch):
    monkeypatch.setenv("PLANOGRAM_PROVIDER", "none")
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    assert not at.exception


def _assert_fallback_pick_fills_query_box(at: AppTest):
    assert not at.exception
    search = next(t for t in at.text_input if t.key == "product_search_text")
    search.input("bre").run()
    picks = [b for b in at.button if b.key and b.key.startswith("suggest_")]
    assert 0 < len(picks) <= 8
    assert all("Level" in b.label and "stock" in b.label.lower() for b in picks)
    first_name = picks[0].label.split(" | ")[0]
    picks[0].click().run()
    assert not at.exception
    assert _query_box_value(at) == first_name


def test_page_falls_back_when_addon_missing(monkeypatch):
    monkeypatch.setenv("PLANOGRAM_PROVIDER", "none")
    monkeypatch.setitem(sys.modules, "streamlit_searchbox", None)  # import now raises ImportError
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    _assert_fallback_pick_fills_query_box(at)


def test_page_falls_back_when_addon_render_fails(monkeypatch):
    streamlit_searchbox = pytest.importorskip("streamlit_searchbox")

    def broken(*args, **kwargs):
        raise RuntimeError("component failed")

    monkeypatch.setenv("PLANOGRAM_PROVIDER", "none")
    monkeypatch.setattr(streamlit_searchbox, "st_searchbox", broken)
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    _assert_fallback_pick_fills_query_box(at)


def test_pick_helper_fills_query_box_with_exact_name(dataset, settings):
    from planogram_agent.ui.streamlit_app import apply_suggestion

    state: dict = {"query_input": "bre"}
    name = suggest("bre", dataset, settings)[0].name
    assert apply_suggestion(state, name) is True
    assert state["query_input"] == name
    assert apply_suggestion(state, name) is False  # same pick again does not re-trigger
    assert apply_suggestion(state, None) is False
