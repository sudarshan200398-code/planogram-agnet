"""Product images: generated SVG placeholders, real files from the store folder, safe fallbacks."""
from __future__ import annotations

import io
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest

import planogram_agent.images as images_module
from planogram_agent.data_loader import load_dataset
from planogram_agent.images import ProductImage, category_colour, initials, placeholder_svg, product_image
from planogram_agent.settings import Settings, load_settings

APP_FILE = str(Path(__file__).resolve().parent.parent / "src" / "planogram_agent" / "ui" / "streamlit_app.py")
STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"
STORE_FILES = ("graph.json", "products.csv", "planogram.csv", "inventory.csv")
SVG_NS = "{http://www.w3.org/2000/svg}"


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(STORE_DIR, validate=True)


@pytest.fixture(scope="module")
def settings():
    return load_settings()


@pytest.fixture
def store(tmp_path):
    """A copy of the demo store with an empty images/ folder."""
    d = tmp_path / "store"
    d.mkdir()
    for f in STORE_FILES:
        shutil.copy(STORE_DIR / f, d / f)
    (d / "images").mkdir()
    return d


def _write_image(path: Path, colour: str, fmt: str, size=(300, 200)) -> None:
    Image.new("RGB", size, colour).save(path, format=fmt)


def _decode(img: ProductImage) -> Image.Image:
    assert isinstance(img.data, bytes)
    return Image.open(io.BytesIO(img.data))


def _svg(img: ProductImage) -> ET.Element:
    assert img.source == "placeholder" and img.mime == "image/svg+xml"
    root = ET.fromstring(img.data)
    assert root.tag == f"{SVG_NS}svg"
    return root


def _title(root: ET.Element) -> str:
    return root.find(f"{SVG_NS}title").text


# ---------- config ----------


def test_image_settings_live_in_config(settings):
    assert settings.image_tile_px == 96
    assert settings.image_max_bytes == 2_000_000
    assert len(settings.image_palette) == 12
    assert all(c.startswith("#") and len(c) == 7 for c in settings.image_palette)
    assert Settings().image_tile_px == 96


# ---------- placeholders ----------


def test_placeholder_exists_for_every_product_sku(dataset, settings):
    for p in dataset.products:
        img = product_image(p.sku, dataset, STORE_DIR, settings)
        root = _svg(img)
        assert img.sku == p.sku
        assert _title(root) == p.name
        assert category_colour(p.category, settings) in img.data


def test_placeholder_is_deterministic_and_cached(dataset, settings):
    p = dataset.products[0]
    a = product_image(p.sku, dataset, STORE_DIR, settings)
    b = product_image(p.sku, dataset, STORE_DIR, settings)
    assert a.data == b.data
    assert a.data is b.data  # second call served from the cache


def test_same_category_same_colour_from_palette(dataset, settings):
    by_cat: dict[str, set[str]] = {}
    for p in dataset.products:
        by_cat.setdefault(p.category, set()).add(category_colour(p.category, settings))
    assert all(len(c) == 1 for c in by_cat.values())
    assert {c for cs in by_cat.values() for c in cs} <= set(settings.image_palette)
    assert len({c for cs in by_cat.values() for c in cs}) > 1


@pytest.mark.parametrize(
    "name, brand, expected",
    [
        ("Daily Bake White Sandwich Bread 400 g", "Daily Bake", "WS"),
        ("White Sandwich Bread", None, "WS"),
        ("Bread", None, "B"),
        ("Store Brand 400 g", "Store Brand", "SB"),  # nothing after the brand but sizes: use the brand
        ("12 Eggs Large", None, "EL"),  # numbers are skipped
        ("café crème", None, "CC"),
        ("", None, "?"),
    ],
)
def test_initials(name, brand, expected):
    assert initials(name, brand) == expected


def test_placeholder_escapes_awkward_names(settings):
    name = 'A & B <Special> "Café" Crème\'s'
    root = ET.fromstring(placeholder_svg(name, "Sauces & dips", None, settings))
    assert _title(root) == name


def test_long_name_wraps_to_two_lines_with_ellipsis(settings):
    name = "Extraordinarily Long Product Name That Goes On And On Far Past Any Tile Width 400 g"
    root = ET.fromstring(placeholder_svg(name, "Misc", None, settings))
    lines = [t.text for t in root.iter(f"{SVG_NS}text") if t.get("class") == "name"]
    assert 1 <= len(lines) <= 2
    assert lines[-1].endswith("…")


def test_unknown_sku_gets_placeholder_not_error(dataset, settings):
    img = product_image("NOT-A-SKU", dataset, STORE_DIR, settings)
    assert _title(_svg(img)) == "NOT-A-SKU"


# ---------- real files ----------


@pytest.mark.parametrize("ext, fmt", [("png", "PNG"), ("jpg", "JPEG")])
def test_real_image_overrides_placeholder(dataset, settings, store, ext, fmt):
    sku = dataset.products[0].sku
    _write_image(store / "images" / f"{sku}.{ext}", "red", fmt)
    img = product_image(sku, dataset, store, settings)
    assert img.source == "file" and img.mime == "image/png"
    pic = _decode(img)
    assert max(pic.size) <= settings.image_tile_px
    r, g, b = pic.convert("RGB").getpixel((pic.width // 2, pic.height // 2))
    assert r > 200 and g < 60 and b < 60


def test_jpg_wins_over_png(dataset, settings, store):
    sku = dataset.products[0].sku
    _write_image(store / "images" / f"{sku}.jpg", "red", "JPEG")
    _write_image(store / "images" / f"{sku}.png", "blue", "PNG")
    pic = _decode(product_image(sku, dataset, store, settings)).convert("RGB")
    r, g, b = pic.getpixel((pic.width // 2, pic.height // 2))
    assert r > 200 and b < 60


def test_replaced_file_shows_new_picture(dataset, settings, store):
    sku = dataset.products[0].sku
    path = store / "images" / f"{sku}.png"
    _write_image(path, "red", "PNG")
    first = product_image(sku, dataset, store, settings).data
    _write_image(path, "blue", "PNG", size=(310, 200))
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    second = product_image(sku, dataset, store, settings).data
    assert first != second


def _make_bad(kind: str, path: Path) -> None:
    if kind == "empty":
        path.write_bytes(b"")
    elif kind == "garbage":
        path.write_bytes(os.urandom(2048))
    elif kind == "truncated":
        buf = io.BytesIO()
        Image.new("RGB", (300, 300), "green").save(buf, format="PNG")
        path.write_bytes(buf.getvalue()[: len(buf.getvalue()) // 3])
    elif kind == "directory":
        path.mkdir()
    elif kind == "text_named_png":
        path.write_text("this is not a picture", encoding="utf-8")


@pytest.mark.parametrize("kind", ["empty", "garbage", "truncated", "directory", "text_named_png"])
def test_missing_or_corrupt_image_falls_back_to_placeholder(dataset, settings, store, kind):
    p = dataset.products[0]
    _make_bad(kind, store / "images" / f"{p.sku}.png")
    img = product_image(p.sku, dataset, store, settings)
    assert _title(_svg(img)) == p.name


def test_corrupt_jpg_falls_back_to_valid_png(dataset, settings, store):
    sku = dataset.products[0].sku
    (store / "images" / f"{sku}.jpg").write_bytes(b"not a jpeg")
    _write_image(store / "images" / f"{sku}.png", "red", "PNG")
    assert product_image(sku, dataset, store, settings).source == "file"


def test_missing_images_folder_falls_back(dataset, settings, store):
    shutil.rmtree(store / "images")
    assert product_image(dataset.products[0].sku, dataset, store, settings).source == "placeholder"


def test_oversize_file_falls_back(dataset, settings, store):
    sku = dataset.products[0].sku
    _write_image(store / "images" / f"{sku}.png", "red", "PNG")
    tiny = settings.model_copy(update={"image_max_bytes": 10})
    assert product_image(sku, dataset, store, tiny).source == "placeholder"


def test_sku_cannot_reach_outside_images_folder(dataset, settings, store):
    _write_image(store / "outside.png", "red", "PNG")
    assert product_image("../outside", dataset, store, settings).source == "placeholder"


def test_store_with_images_folder_still_loads(store):
    _write_image(store / "images" / "ANY.png", "red", "PNG")
    assert len(load_dataset(store, validate=True).products) == len(load_dataset(STORE_DIR).products)


def test_nothing_raises_for_any_product_with_bad_files(dataset, settings, store):
    for p in dataset.products[::7]:
        (store / "images" / f"{p.sku}.jpg").write_bytes(os.urandom(64))
    for p in dataset.products:
        assert product_image(p.sku, dataset, store, settings).sku == p.sku


# ---------- page ----------


@pytest.fixture
def spy(monkeypatch):
    """Record (sku, source) for every picture the page asks for."""
    seen: list[tuple[str, str]] = []
    real = images_module.product_image

    def recording(sku, dataset, store_dir, settings):
        img = real(sku, dataset, store_dir, settings)
        seen.append((sku, img.source))
        return img

    monkeypatch.setattr(images_module, "product_image", recording)
    monkeypatch.setenv("PLANOGRAM_PROVIDER", "none")
    return seen


def _new_app() -> AppTest:
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    assert not at.exception
    return at


# The old example button's text, now typed into the paste box and run with Find
MULTI_EXAMPLE = "Store Brand Shredded Cheddar 400 g and Daily Bake White Sandwich Bread 400 g"


def _search(at: AppTest, text: str) -> None:
    at.text_area[0].input(text)
    at.button(key="find").click().run()


def _basket_panel(at: AppTest):
    """The main-page basket container (it used to be the sidebar)."""
    def blocks(node):
        for child in getattr(node, "children", {}).values():
            yield child
            yield from blocks(child)

    return next(b for b in blocks(at.main) if str(getattr(getattr(b, "proto", None), "id", "")).endswith("-basket_panel"))


def test_item_cards_show_images(spy):
    at = _new_app()
    _search(at, MULTI_EXAMPLE)
    assert not at.exception
    found = [it.sku for it in at.session_state["last_answer"].items if it.sku]
    assert found and set(found) <= {sku for sku, _ in spy}
    assert len(at.get("image")) >= len(found)


def test_basket_rows_show_images(spy):
    at = _new_app()
    _search(at, MULTI_EXAMPLE)
    for b in [b for b in at.button if b.key and b.key.startswith("add_item_")]:
        b.click().run()
    assert not at.exception
    assert len(_basket_panel(at).get("image")) == len(at.session_state["basket"]) == 2


def test_fallback_suggestion_rows_show_images(spy, monkeypatch):
    monkeypatch.setitem(sys.modules, "streamlit_searchbox", None)
    at = _new_app()
    spy.clear()
    next(t for t in at.text_input if t.key == "product_search_text").input("bre").run()
    assert not at.exception
    rows = [b.key.removeprefix("suggest_") for b in at.button if b.key and b.key.startswith("suggest_")]
    assert rows and set(rows) <= {sku for sku, _ in spy}


def test_picked_dropdown_product_shows_image(spy, monkeypatch, dataset):
    streamlit_searchbox = pytest.importorskip("streamlit_searchbox")
    sku = dataset.products[0].sku
    picks = [("product", sku)]  # the add-on reports one pick of this product

    def fake(*args, submit_function=None, **kwargs):
        if picks:
            submit_function(picks.pop(0))

    monkeypatch.setattr(streamlit_searchbox, "st_searchbox", fake)
    at = _new_app()
    assert (sku, "placeholder") in spy


def test_page_uses_real_image_from_store_folder(spy, store):
    at = _new_app()
    _search(at, MULTI_EXAMPLE)
    sku = next(it.sku for it in at.session_state["last_answer"].items if it.sku)
    _write_image(store / "images" / f"{sku}.png", "red", "PNG")
    next(t for t in at.sidebar.text_input if t.label == "Store folder").set_value(str(store)).run()
    spy.clear()
    at.button(key="find").click().run()
    assert not at.exception
    assert (sku, "file") in spy
