"""Tests for Phase 8: Streamlit UI and map visualization."""
from __future__ import annotations

from pathlib import Path

import matplotlib.figure
import pytest
from streamlit.testing.v1 import AppTest

from planogram_agent.data_loader import load_dataset
from planogram_agent.graph import build_graph, shortest_path
from planogram_agent.interface import create_finder, run_query
from planogram_agent.llm.no_model import NoModelClient
from planogram_agent.schemas import ConnectorType
from planogram_agent.settings import Settings
from planogram_agent.ui.map_plot import draw_floor, get_floor_stops

APP_FILE = str(Path(__file__).resolve().parent.parent / "src" / "planogram_agent" / "ui" / "streamlit_app.py")
STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(STORE_DIR, validate=True)


@pytest.fixture(scope="module")
def settings():
    return Settings()


@pytest.fixture(autouse=True)
def configure_ui_provider(monkeypatch):
    monkeypatch.setenv("PLANOGRAM_PROVIDER", "none")


def test_page_loads():
    """Streamlit page loads cleanly with no exceptions."""
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    assert not at.exception
    assert len(at.title) >= 1
    assert "Store Product Finder" in at.title[0].value
    assert len(at.selectbox) >= 1
    assert at.selectbox(key="start_point").value == "Use my message, or the entrance"


def test_plain_bagels_gives_ok_answer_with_route():
    """'Daily Bake Plain Bagels 4 pack' gives an ok answer with a route."""
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.text_area[0].input("Daily Bake Plain Bagels 4 pack")
    # Button index 3 is 'Find'
    at.button(key="find").click().run()

    assert not at.exception
    ans = at.session_state.last_answer
    assert ans is not None
    assert ans.status == "ok"
    assert ans.route is not None
    assert ans.route.start_label == "Entrance"
    assert len(ans.items) == 1
    assert ans.items[0].sku == "BAK-BAG-009"
    assert ans.items[0].status == "available"

    # Verify markdown rendered on page
    markdown_texts = [m.value for m in at.markdown]
    assert any("Daily Bake Plain Bagels 4 pack" in t for t in markdown_texts)
    assert any("Status: Available" in t for t in markdown_texts)
    assert any("Walk" in t for t in markdown_texts)


def test_milk_shows_options_and_choice_gives_answer():
    """'milk' presents clarification options; choosing one yields a completed answer."""
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.text_area[0].input("milk")
    at.button(key="find").click().run()

    assert not at.exception
    ans = at.session_state.last_answer
    assert ans is not None
    assert ans.status == "needs_clarification"
    assert ans.question is not None

    # Clarification buttons are now rendered
    button_labels = [b.label for b in at.button]
    assert any("Meadow Fresh Whole Milk 1 L" in lbl for lbl in button_labels)

    # Click the first clarification choice button (index 4)
    next(b for b in at.button if b.key and b.key.startswith("opt_")).click().run()

    assert not at.exception
    resolved_ans = at.session_state.last_answer
    assert resolved_ans is not None
    assert resolved_ans.status == "ok"
    assert resolved_ans.route is not None
    assert resolved_ans.items[0].status == "available"
    assert "Milk" in resolved_ans.items[0].name


def test_empty_text_shows_message():
    """Submitting empty text shows an informative message without crashing."""
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.text_area[0].input("   ")
    at.button(key="find").click().run()

    assert not at.exception
    assert len(at.info) >= 1
    assert "Please enter a product name" in at.info[0].value
    assert at.session_state.last_answer is None


def test_message_with_default_sidebar_starts_at_bakery():
    """A message 'Daily Bake Plain Bagels 4 pack, I'm near the Bakery' with default sidebar starts at the Bakery."""
    query = "Daily Bake Plain Bagels 4 pack, I'm near the Bakery"
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.text_area[0].input(query)
    at.button(key="find").click().run()

    assert not at.exception
    ans = at.session_state.last_answer
    assert ans is not None
    assert ans.route is not None
    assert ans.route.start_label == "Bakery"


def test_message_with_sidebar_produce_starts_at_produce():
    """The same message 'Daily Bake Plain Bagels 4 pack, I'm near the Bakery' with sidebar set to Produce starts at Produce."""
    query = "Daily Bake Plain Bagels 4 pack, I'm near the Bakery"
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.selectbox(key="start_point").select("Produce")
    at.text_area[0].input(query)
    at.button(key="find").click().run()

    assert not at.exception
    ans = at.session_state.last_answer
    assert ans is not None
    assert ans.route is not None
    assert ans.route.start_label == "Produce"


def test_step_free_toggle_gives_route_without_stairs_or_escalators():
    """Enabling the step-free toggle produces a route with no stairs or escalators."""
    query = "Store Brand Baseball Cap one size"

    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.toggle(key="step_free").set_value(True)
    at.text_area[0].input(query)
    at.button(key="find").click().run()

    assert not at.exception
    ans = at.session_state.last_answer
    assert ans is not None
    assert ans.route is not None
    assert ans.route.accessible_only is True
    assert ConnectorType.STAIRS not in ans.route.connectors_used
    assert ConnectorType.ESCALATOR not in ans.route.connectors_used
    assert ConnectorType.ELEVATOR in ans.route.connectors_used


def test_map_plot_draw_floor_two_floor_route(dataset, settings):
    """draw_floor returns a matplotlib Figure with the right number of stops for a two-floor route."""
    finder = create_finder(STORE_DIR, settings=settings, client=NoModelClient())
    ans = run_query(finder, "Daily Bake Plain Bagels 4 pack and Store Brand Baseball Cap one size")
    assert ans.status == "ok"
    assert ans.route is not None
    assert ans.route.floor_changes >= 1

    l1_stops = get_floor_stops(ans, floor=1)
    l2_stops = get_floor_stops(ans, floor=2)
    assert len(l1_stops) == 1
    assert len(l2_stops) == 1
    assert l1_stops[0][0] == 1
    assert l2_stops[0][0] == 2

    fig1 = draw_floor(dataset, ans, floor=1)
    assert isinstance(fig1, matplotlib.figure.Figure)

    fig2 = draw_floor(dataset, ans, floor=2)
    assert isinstance(fig2, matplotlib.figure.Figure)

    single_floor_ans = run_query(finder, "Daily Bake Plain Bagels 4 pack")
    fig_empty = draw_floor(dataset, single_floor_ans, floor=2)
    assert isinstance(fig_empty, matplotlib.figure.Figure)
    ax = fig_empty.axes[0]
    texts = [t.get_text() for t in ax.texts]
    assert any("no route on this floor" in t.lower() for t in texts)


def test_item_cards_match_inventory_and_planogram_data(dataset):
    """For each item card the displayed quantity equals the stock file's quantity and location matches planogram."""
    query = "Store Brand Shredded Cheddar 400 g and Daily Bake White Sandwich Bread 400 g"
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.text_area[0].input(query)
    at.button(key="find").click().run()

    assert not at.exception
    ans = at.session_state.last_answer
    assert ans is not None

    inv_map = {item.sku: item.quantity for item in dataset.inventory}
    plan_rows = {
        (e.sku, e.floor, e.zone, e.bay, e.shelf_level)
        for e in dataset.planogram
    }

    markdown_texts = [m.value for m in at.markdown]

    for item in ans.items:
        assert item.sku in inv_map, f"SKU {item.sku} not in inventory"
        expected_qty = inv_map[item.sku]
        assert item.quantity == expected_qty

        # Verify page displays the exact quantity
        assert any("Status: Available" in t for t in markdown_texts)
        expected_status_str = f"In stock: {expected_qty}"
        assert any(expected_status_str in t for t in markdown_texts), (
            f"Expected '{expected_status_str}' rendered on page"
        )

        # Verify page displays valid planogram location
        assert item.chosen_location is not None
        loc = item.chosen_location
        loc_key = (item.sku, loc.floor, loc.zone, loc.bay, loc.shelf_level)
        assert loc_key in plan_rows, f"Rendered location {loc_key} not in planogram"
        for expected_loc_str in (f"Level {loc.floor} · {loc.zone}", f"Bay {loc.bay} · Shelf {loc.shelf_level}"):
            assert any(expected_loc_str in t for t in markdown_texts), (
                f"Expected '{expected_loc_str}' rendered on page"
            )


def test_example1_directions_and_summary_distance(dataset):
    """Example 1 directions first arrive step names Bakery product and summary matches independent router calculation."""
    query = "Store Brand Shredded Cheddar 400 g and Daily Bake White Sandwich Bread 400 g"
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.text_area[0].input(query)
    at.button(key="find").click().run()

    assert not at.exception
    ans = at.session_state.last_answer
    assert ans is not None
    assert ans.route is not None

    # Directions check: first arrive step must name the Bakery product
    arrive_steps = [s for s in ans.route.steps if s.kind == "arrive"]
    assert len(arrive_steps) >= 2
    assert "Daily Bake White Sandwich Bread" in (arrive_steps[0].product_name or "")
    assert "Store Brand Shredded Cheddar" in (arrive_steps[1].product_name or "")

    # Independent distance computation using graph and router:
    # Entrance (L1_ENTRANCE) -> Bakery (L1_BAKERY) -> Dairy & Frozen (L1_DAIRY)
    G = build_graph(dataset.graph)
    leg1 = shortest_path(G, "L1_ENTRANCE", "L1_BAKERY")
    leg2 = shortest_path(G, "L1_BAKERY", "L1_DAIRY")
    independent_walking_dist = leg1.walking_distance + leg2.walking_distance
    independent_rounded = round(independent_walking_dist)

    expected_summary_text = f"about {independent_rounded} m of walking, 0 floor change(s)"
    assert expected_summary_text == "about 72 m of walking, 0 floor change(s)"

    # Verify literal "about 72 m" rendered on page
    markdown_texts = [m.value for m in at.markdown]
    assert any("about 72 m" in t for t in markdown_texts)
    assert any(expected_summary_text in t for t in markdown_texts)


def test_milk_flow_shows_stock_quantity(dataset):
    """For the milk flow, after choosing option 1, the page displays the real inventory quantity 61."""
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.text_area[0].input("milk")
    at.button(key="find").click().run()

    assert not at.exception
    # Click option 1 (Meadow Fresh Whole Milk 1 L, DAI-MIL-001)
    next(b for b in at.button if b.key and b.key.startswith("opt_")).click().run()

    assert not at.exception
    ans = at.session_state.last_answer
    assert ans is not None
    assert ans.items[0].sku == "DAI-MIL-001"

    # Ground truth quantity from inventory.csv
    milk_inv = next(i.quantity for i in dataset.inventory if i.sku == "DAI-MIL-001")
    assert milk_inv == 61
    assert ans.items[0].quantity == 61

    # Verify card on page shows quantity 61
    markdown_texts = [m.value for m in at.markdown]
    assert any("In stock: 61" in t for t in markdown_texts)
    assert any("Status: Available" in t for t in markdown_texts)


def test_out_of_stock_example_data_integrity(dataset):
    """Out-of-stock example ('ArtBox Watercolour Paints 12 pack') shows words 'Out of stock', qty 0, real location, no route."""
    query = "ArtBox Watercolour Paints 12 pack"
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.text_area[0].input(query)
    at.button(key="find").click().run()

    assert not at.exception
    ans = at.session_state.last_answer
    assert ans is not None
    assert ans.status == "partial"
    assert ans.route is None  # no route for out-of-stock item

    item = ans.items[0]
    assert item.sku == "TOY-ART-005"
    assert item.status == "unavailable"
    assert item.quantity == 0

    # Ground truth location from planogram
    plan_entry = next(e for e in dataset.planogram if e.sku == "TOY-ART-005")
    assert item.chosen_location is not None
    assert item.chosen_location.floor == plan_entry.floor == 2
    assert item.chosen_location.zone == plan_entry.zone == "Toys & Stationery"
    assert item.chosen_location.bay == plan_entry.bay == "C"
    assert item.chosen_location.shelf_level == plan_entry.shelf_level == 2

    # Verify rendered texts
    markdown_texts = [m.value for m in at.markdown]
    assert any("Status: Out of stock" in t for t in markdown_texts)
    assert any("Level 2 · Toys & Stationery" in t for t in markdown_texts)
    assert any("Bay C · Shelf 2" in t for t in markdown_texts)
    assert any("Out of stock" in (c.value or "") for c in at.caption)


def test_unknown_planogram_provider_uses_no_model_and_does_not_crash(monkeypatch):
    """Unknown PLANOGRAM_PROVIDER uses NoModelClient, sets model_note, and does not crash UI."""
    import streamlit as st
    st.cache_resource.clear()
    try:
        monkeypatch.setenv("PLANOGRAM_PROVIDER", "bogus_provider_xyz")
        finder = create_finder(STORE_DIR)
        assert isinstance(finder.client, NoModelClient)
        assert finder.model_note is not None
        assert "bogus_provider_xyz" in finder.model_note

        at = AppTest.from_file(APP_FILE, default_timeout=30)
        at.run()
        assert not at.exception
        assert any("bogus_provider_xyz" in s.value for s in at.sidebar.text)
    finally:
        st.cache_resource.clear()
