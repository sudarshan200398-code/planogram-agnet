"""Each route leg is drawn on its own floor, and the page shows every floor map with its stops."""
from __future__ import annotations

import itertools
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from planogram_agent.data_loader import load_dataset
from planogram_agent.interface import answer_question, create_finder, run_query
from planogram_agent.llm.no_model import NoModelClient
from planogram_agent.schemas import ConnectorType
from planogram_agent.settings import Settings
from planogram_agent.ui.map_plot import (
    clarification_option_label,
    draw_floor,
    floor_change_lines,
    floor_change_nodes,
    floor_display_order,
    route_floor_segments,
)

APP_FILE = str(Path(__file__).resolve().parent.parent / "src" / "planogram_agent" / "ui" / "streamlit_app.py")
STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"

ROUTE_COLOR = "#2563eb"
CONNECTOR_RING_COLOR = (0.8627450980392157, 0.14901960784313725, 0.14901960784313725, 1.0)  # "#dc2626"

L2_GIFT_CARD = "CUS-GIF-001"  # Customer Service & Payment Hub, Level 2
L1_GIFT_CARD = "CHK-BAT-007"  # Checkout, Level 1


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(STORE_DIR, validate=True)


@pytest.fixture(scope="module")
def finder():
    return create_finder(STORE_DIR, settings=Settings(), client=NoModelClient())


@pytest.fixture(scope="module")
def node_floor(dataset):
    return {n.id: n.floor for n in dataset.graph.nodes}


def _choose(finder, text, sku, accessible_only=None):
    ans = run_query(finder, text, accessible_only=accessible_only)
    while ans.status == "needs_clarification":
        ans = answer_question(finder, session_id=ans.session_id, item_index=ans.question.item_index, sku=sku)
    return ans


def _drawn_route_segments(fig):
    ax = fig.axes[0]
    return [
        (tuple(line.get_xdata()), tuple(line.get_ydata()))
        for line in ax.lines
        if line.get_color() == ROUTE_COLOR
    ]


def _drawn_connector_rings(fig):
    ax = fig.axes[0]
    points = []
    for coll in ax.collections:
        edges = coll.get_edgecolors()
        faces = coll.get_facecolors()
        if len(edges) and tuple(edges[0]) == CONNECTOR_RING_COLOR and len(faces) == 0:
            points.extend(tuple(p) for p in coll.get_offsets())
    return points


def _assert_legs_drawn_on_their_floors(dataset, ans, node_floor):
    """Every same-floor pair of the route path is drawn once, on that floor, and nowhere else."""
    nodes = {n.id: n for n in dataset.graph.nodes}
    path = ans.route.path
    for fl in dataset.graph.floors:
        expected = sorted(
            ((nodes[u].x, nodes[v].x), (nodes[u].y, nodes[v].y))
            for u, v in itertools.pairwise(path)
            if node_floor[u] == fl and node_floor[v] == fl
        )
        drawn = sorted(_drawn_route_segments(draw_floor(dataset, ans, fl)))
        assert drawn == expected, f"Level {fl}: drawn route segments do not match the route path"


def _assert_connectors_ringed(dataset, ans, node_floor):
    """At each floor change, the connector node is ringed on both floors it joins."""
    nodes = {n.id: n for n in dataset.graph.nodes}
    for u, v in itertools.pairwise(ans.route.path):
        if node_floor[u] != node_floor[v]:
            for nid in (u, v):
                rings = _drawn_connector_rings(draw_floor(dataset, ans, node_floor[nid]))
                assert (nodes[nid].x, nodes[nid].y) in rings, f"connector {nid} not ringed on Level {node_floor[nid]}"


# ---------- draw_floor: each leg on its own floor ----------


def test_level2_only_item_draws_on_both_floors(dataset, finder, node_floor):
    ans = _choose(finder, "gift cards", L2_GIFT_CARD)
    assert ans.status == "ok"
    assert ans.items[0].chosen_location.floor == 2
    assert ans.route.floor_changes == 1

    segs = route_floor_segments(dataset, ans)
    assert segs[1], "Level 1 should carry the walk from the entrance to the connector"
    assert segs[2], "Level 2 should carry the walk from the connector to the stop"
    for fl, pairs in segs.items():
        assert all(node_floor[u] == fl and node_floor[v] == fl for u, v in pairs)

    _assert_legs_drawn_on_their_floors(dataset, ans, node_floor)
    _assert_connectors_ringed(dataset, ans, node_floor)

    fig2 = draw_floor(dataset, ans, 2)
    assert "no route" not in fig2.axes[0].get_title().lower()
    assert any(t.get_text() == "1" for t in fig2.axes[0].texts), "stop 1 should be marked on Level 2"


def test_mixed_list_draws_each_stop_on_its_floor(dataset, finder, node_floor):
    ans = run_query(finder, "Daily Bake Plain Bagels 4 pack and Store Brand Baseball Cap one size")
    assert ans.status == "ok"
    floors_of_stops = {it.chosen_location.floor for it in ans.items}
    assert floors_of_stops == {1, 2}

    segs = route_floor_segments(dataset, ans)
    assert segs[1] and segs[2]
    _assert_legs_drawn_on_their_floors(dataset, ans, node_floor)
    _assert_connectors_ringed(dataset, ans, node_floor)


def test_step_free_route_uses_elevator_on_both_floors(dataset, finder, node_floor):
    ans = _choose(finder, "gift cards", L2_GIFT_CARD, accessible_only=True)
    assert ans.route.accessible_only is True
    assert ans.route.connectors_used == [ConnectorType.ELEVATOR]

    changes = floor_change_nodes(dataset, ans)
    nodes = {n.id: n for n in dataset.graph.nodes}
    assert set(changes) == {1, 2}
    for fl, ids in changes.items():
        assert ids and all(nodes[i].floor == fl and nodes[i].type.value == "elevator" for i in ids)

    _assert_legs_drawn_on_their_floors(dataset, ans, node_floor)
    _assert_connectors_ringed(dataset, ans, node_floor)


def test_level1_item_draws_nothing_on_level2(dataset, finder):
    ans = _choose(finder, "gift cards", L1_GIFT_CARD)
    assert ans.items[0].chosen_location.floor == 1
    assert route_floor_segments(dataset, ans).get(2, []) == []
    fig2 = draw_floor(dataset, ans, 2)
    assert _drawn_route_segments(fig2) == []
    assert "no route" in fig2.axes[0].get_title().lower()


# ---------- page helpers ----------


def test_floor_display_order_puts_first_stop_floor_first(dataset, finder):
    l2 = _choose(finder, "gift cards", L2_GIFT_CARD)
    l1 = _choose(finder, "gift cards", L1_GIFT_CARD)
    assert floor_display_order(dataset, l2) == [2, 1]
    assert floor_display_order(dataset, l1) == [1, 2]
    assert floor_display_order(dataset, None) == [1, 2]


def test_floor_change_lines(finder):
    l2 = _choose(finder, "gift cards", L2_GIFT_CARD)
    l1 = _choose(finder, "gift cards", L1_GIFT_CARD)
    assert floor_change_lines(l2) == ["Take the stairs from Level 1 to Level 2."]
    assert floor_change_lines(l1) == []


def test_clarification_option_label_shows_floor_and_zone(dataset):
    assert clarification_option_label(dataset, L2_GIFT_CARD, "PowerTech Store Gift Card 10 value") == (
        "PowerTech Store Gift Card 10 value, Level 2, Customer Service & Payment Hub"
    )
    plan = next(e for e in dataset.planogram if e.sku == L1_GIFT_CARD)
    assert clarification_option_label(dataset, L1_GIFT_CARD, "Quick Pick Gift Card 8 pack") == (
        f"Quick Pick Gift Card 8 pack, Level 1, {plan.zone}"
    )
    assert clarification_option_label(dataset, "NO-SUCH-SKU", "Thing") == "Thing, no shelf location"


# ---------- the real page flow ----------


def _run_gift_cards_and_pick(level: int) -> AppTest:
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.text_area[0].input("gift cards")
    at.button(key="find").click().run()
    assert not at.exception
    assert at.session_state.last_answer.status == "needs_clarification"

    choices = [b for b in at.button if f", Level {level}, " in b.label]
    assert choices, f"no clarification choice labelled with Level {level}: {[b.label for b in at.button]}"
    choices[0].click().run()
    assert not at.exception
    return at


def _floor_sections(at: AppTest) -> list[tuple[str, str]]:
    """(heading, caption) for each floor map, in page order, each followed by its map image."""
    flat = list(at.main)  # iterating a block yields every nested element in page order
    sections = []
    for i, e in enumerate(flat):
        if type(e).__name__ == "Markdown" and str(e.value).startswith("#### Level "):
            img = next((x for x in flat[i + 1:] if type(x).__name__ == "Image"), None)
            cap = next((x for x in flat[i + 1:] if type(x).__name__ == "Caption"), None)
            assert img is not None, f"{e.value} has no map image"
            sections.append((e.value.removeprefix("#### "), cap.value if cap else ""))
    return sections


def test_page_level2_choice_shows_level2_text_and_map(dataset):
    at = _run_gift_cards_and_pick(level=2)
    ans = at.session_state.last_answer
    assert ans.status == "ok"
    assert ans.items[0].sku == L2_GIFT_CARD

    texts = [m.value for m in at.markdown]
    assert any("Take the stairs from Level 1 to Level 2." in t for t in texts)
    assert any("Arrive at Customer Service & Payment Hub" in t and "Level 2" in t for t in texts)
    # one plain floor-change line under the route
    assert "Take the stairs from Level 1 to Level 2." in [m.value for m in at.markdown if m.value.startswith("Take ")]

    sections = _floor_sections(at)
    assert [h for h, _ in sections] == ["Level 2", "Level 1"]
    assert "Stops on Level 2: 1. PowerTech Store Gift Card 10 value" in sections[0][1]
    assert "route passes through" in sections[1][1].lower()

    segs = route_floor_segments(dataset, ans)
    assert segs[2] and segs[1]


def test_page_level1_choice_shows_no_level2_route(dataset):
    at = _run_gift_cards_and_pick(level=1)
    ans = at.session_state.last_answer
    assert ans.status == "ok"
    assert ans.items[0].sku == L1_GIFT_CARD
    assert ans.route.floor_changes == 0

    texts = " ".join(m.value for m in at.markdown)
    assert "Level 2" not in ans.route.directions_text
    assert "Take the" not in texts

    sections = _floor_sections(at)
    assert [h for h, _ in sections] == ["Level 1", "Level 2"]
    assert "Stops on Level 1: 1. Quick Pick Gift Card 8 pack" in sections[0][1]
    assert sections[1][1] == "No route on Level 2"

    assert route_floor_segments(dataset, ans).get(2, []) == []
