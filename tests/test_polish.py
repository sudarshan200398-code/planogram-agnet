"""Polish and deployment readiness: card and route labels, config files, pins, no keys in the repo."""
from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from planogram_agent.agents.routing import DirectionStep, format_direction_step
from planogram_agent.interface import create_finder, run_query
from planogram_agent.llm.no_model import NoModelClient
from planogram_agent.schemas import ConnectorType
from planogram_agent.ui.present import STEP_ICONS, card_lines, status_badge, step_rows

ROOT = Path(__file__).resolve().parent.parent
APP_FILE = str(ROOT / "src" / "planogram_agent" / "ui" / "streamlit_app.py")
STORE_DIR = ROOT / "data" / "store_demo"
KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_\-]{35}|sk-ant-[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9]{32,}")


@pytest.fixture(scope="module")
def finder():
    return create_finder(STORE_DIR, client=NoModelClient())


# ---------- route steps ----------


def _steps() -> list[DirectionStep]:
    return [
        DirectionStep(kind="walk", floor=1, from_label="Entrance", to_label="Bakery", distance=33.0),
        DirectionStep(kind="take_connector", floor=1, to_floor=2, connector_type=ConnectorType.STAIRS),
        DirectionStep(kind="take_connector", floor=2, to_floor=1, connector_type=ConnectorType.ESCALATOR),
        DirectionStep(kind="take_connector", floor=1, to_floor=2, connector_type=ConnectorType.ELEVATOR),
        DirectionStep(kind="arrive", floor=2, to_label="Toys", product_name="Paints", location_text="Level 2, Toys"),
    ]


def test_step_rows_keep_order_wording_and_icons():
    steps = _steps()
    rows = step_rows(steps)
    assert [text for _, text in rows] == [format_direction_step(s) for s in steps]
    assert [icon for icon, _ in rows] == [
        STEP_ICONS["walk"], STEP_ICONS["stairs"], STEP_ICONS["escalator"], STEP_ICONS["elevator"], STEP_ICONS["arrive"],
    ]
    assert len(set(STEP_ICONS.values())) == 5
    assert all(icon.startswith(":material/") for icon in STEP_ICONS.values())


def test_step_rows_match_a_real_route(finder):
    ans = run_query(finder, "Daily Bake Plain Bagels 4 pack")
    rows = step_rows(ans.route.steps)
    assert rows
    assert [text for _, text in rows] == [format_direction_step(s) for s in ans.route.steps]
    assert all(text in ans.route.directions_text for _, text in rows)


# ---------- cards ----------


@pytest.mark.parametrize(
    "status, colour, text",
    [
        ("available", "green", "Status: Available"),
        ("unavailable", "red", "Status: Out of stock"),
        ("needs_choice", "orange", "Status: Needs choice"),
        ("not_found", "gray", "Status: Not found in catalogue"),
        ("not_placed", "gray", "Status: Not placed on shelves"),
        ("error", "gray", "Status: Error"),
    ],
)
def test_status_badge_colours(status, colour, text):
    assert status_badge(status) == (colour, text)


def test_card_lines_show_place_and_in_stock(finder):
    ans = run_query(finder, "Daily Bake Plain Bagels 4 pack")
    item = ans.items[0]
    loc = item.chosen_location
    inv = next(i.quantity for i in finder.dataset.inventory if i.sku == item.sku)
    assert card_lines(item) == [f"Level {loc.floor} · {loc.zone}", f"Bay {loc.bay} · Shelf {loc.shelf_level}", f"In stock: {inv}"]


def test_card_lines_out_of_stock_has_no_in_stock_line(finder):
    item = run_query(finder, "ArtBox Watercolour Paints 12 pack").items[0]
    assert card_lines(item) == ["Level 2 · Toys & Stationery", "Bay C · Shelf 2"]


# ---------- config and deployment files ----------


def test_streamlit_config_parses_and_sets_theme():
    cfg = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    theme = cfg["theme"]
    assert theme["base"] == "light"
    assert theme["primaryColor"] == "#0F5257"
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", theme["backgroundColor"])
    assert cfg["client"]["toolbarMode"] == "minimal"


def test_secrets_example_has_placeholders_only():
    example = tomllib.loads((ROOT / ".streamlit" / "secrets.toml.example").read_text(encoding="utf-8"))
    assert set(example) == {"PLANOGRAM_PROVIDER", "GEMINI_API_KEY"}
    assert example["PLANOGRAM_PROVIDER"] in ("none", "gemini")
    assert not KEY_PATTERN.search(example["GEMINI_API_KEY"])
    assert "your" in example["GEMINI_API_KEY"].lower()


def test_real_secrets_file_is_ignored():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".streamlit/secrets.toml" in lines
    assert ".env" in lines


def test_requirements_pin_the_three_runtime_packages():
    lines = [l.strip() for l in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert lines == [".[ui]", "streamlit==1.66.0", "streamlit-searchbox==0.1.24", "google-genai==2.30.1"]
    for line in lines[1:]:
        name, pinned = line.split("==")
        assert version(name) == pinned, f"{name}: installed {version(name)}, pinned {pinned}"


def test_no_api_key_anywhere_in_tracked_files():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    assert files
    hits = []
    for f in files:
        try:
            text = (ROOT / f).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits += [f"{f}:{text.count(chr(10), 0, m.start()) + 1}" for m in KEY_PATTERN.finditer(text)]
    assert hits == []


def test_readme_has_deployment_sections():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for heading in ("### Run locally", "### Run the tests", "### Deploy on Streamlit Cloud", "### Turn the AI model on or off"):
        assert heading in readme


# ---------- page ----------


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("PLANOGRAM_PROVIDER", "none")
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def _texts(at: AppTest) -> list[str]:
    return [m.value for m in at.markdown] + [c.value for c in at.caption]


def test_header_chip_shows_model_off(app):
    assert "Store Product Finder" in app.title[0].value
    assert any("AI model: off" in t for t in _texts(app))


def test_no_examples_or_how_it_works_and_hint_line_present(app):
    from planogram_agent.ui.streamlit_app import SEARCH_HINT

    assert not any("How it works" in t for t in _texts(app))
    keys = {b.key for b in app.button}
    assert "find" in keys
    assert not keys & {"example_multi", "example_milk", "example_oos"}
    assert any(c.value == SEARCH_HINT for c in app.caption)
    app.text_area[0].input("Daily Bake Plain Bagels 4 pack")
    app.button(key="find").click().run()
    assert not app.exception
    keys = {b.key for b in app.button}
    assert not keys & {"example_multi", "example_milk", "example_oos"}
    assert not any("How it works" in t for t in _texts(app))


def test_search_placeholder_and_start_row(app):
    assert app.text_area[0].placeholder == "Type a product or a list, for example: milk, bread, rice cooker"
    assert app.selectbox(key="start_point").value == "Use my message, or the entrance"
    assert app.toggle(key="step_free").value is False


def test_results_use_in_stock_label_and_route_tiles(app):
    app.text_area[0].input("Daily Bake Plain Bagels 4 pack")
    app.button(key="find").click().run()
    texts = _texts(app)
    assert not any("Quantity" in t for t in texts)
    assert any(t.startswith("In stock: ") for t in texts)
    assert any(s.value == "Your route" for s in app.subheader)
    assert [m.label for m in app.metric] == ["Walking distance", "Floor changes"]
    assert any(STEP_ICONS["walk"] in t for t in texts)
    assert any(STEP_ICONS["arrive"] in t for t in texts)
    assert any("Demo data" in t for t in texts)


def test_wrong_store_folder_shows_friendly_message(app):
    next(t for t in app.sidebar.text_input if t.label == "Store folder").set_value("no/such/store").run()
    assert not app.exception
    assert any("couldn't open the store folder" in e.value for e in app.error)


def test_fallback_rows_say_add(monkeypatch):
    monkeypatch.setenv("PLANOGRAM_PROVIDER", "none")
    monkeypatch.setitem(sys.modules, "streamlit_searchbox", None)
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.text_input(key="product_search_text").input("bre").run()
    adds = [b for b in at.button if b.key and b.key.startswith("add_suggest_")]
    assert adds and all(b.label == "Add" for b in adds)
