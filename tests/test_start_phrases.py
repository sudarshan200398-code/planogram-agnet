"""Start-point phrases in the rule-based parser: first-person and 'start/currently' forms, with and
without apostrophes, any case, optional 'the' and section/area/zone/department. Model off."""
from __future__ import annotations

from pathlib import Path

import pytest

from planogram_agent.agents.query import parse_request
from planogram_agent.data_loader import load_dataset
from planogram_agent.llm.no_model import NoModelClient
from planogram_agent.settings import load_settings

STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"

FIRST_PERSON = ["im ", "i'm ", "i’m ", "i am "]  # no apostrophe, straight, curly, full
FIRST_PERSON_TAILS = ["at", "near", "in", "standing at", "standing near"]
OTHER_FORMS = ["starting from", "start at", "start from", "from", "currently at", "currently in", "currently near"]
FORMS = [p + t for p in FIRST_PERSON for t in FIRST_PERSON_TAILS] + OTHER_FORMS
ZONES = ["produce", "the produce", "the produce section", "produce area"]
CASES = {"lower": str.lower, "upper": str.upper, "title": str.title}


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(STORE_DIR, validate=True)


@pytest.fixture(scope="module")
def settings():
    return load_settings()


def _parse(text, dataset, settings):
    r = parse_request(text, client=NoModelClient(), settings=settings, dataset=dataset)
    return r.start, [i.text.lower() for i in r.items]


# ---------- every requested form ----------


@pytest.mark.parametrize("case", list(CASES))
@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("form", FORMS)
def test_start_phrase_forms(dataset, settings, form, zone, case):
    text = CASES[case](f"{form} {zone}, milk and crayons")
    assert _parse(text, dataset, settings) == ("Produce", ["milk", "crayons"]), text


# ---------- the reported sentences ----------


@pytest.mark.parametrize(
    "text, items",
    [
        ("im at produce, milk, bred and crayons", ["milk", "bred", "crayons"]),
        ("im near produce and i want milk", ["milk"]),
        ("I am at produce, milk, bred and crayons", ["milk", "bred", "crayons"]),
        ("I am at produce area, milk and crayons", ["milk", "crayons"]),
    ],
)
def test_reported_sentences(dataset, settings, text, items):
    assert _parse(text, dataset, settings) == ("Produce", items)


@pytest.mark.parametrize(
    "text, start, items",
    [
        ("i’m near the dairy & frozen section and i want milk", "Dairy & Frozen", ["milk"]),
        ("Im in the bakery department, i need milk and get me crayons", "Bakery", ["milk", "crayons"]),
        ("currently at checkout zone, get me milk", "Checkout zone", ["milk"]),
        ("start from the café area; milk", "Café", ["milk"]),
    ],
)
def test_lead_in_words_never_become_products(dataset, settings, text, start, items):
    assert _parse(text, dataset, settings) == (start, items)


# ---------- forms that already worked stay working ----------


@pytest.mark.parametrize(
    "text, start, items",
    [
        ("I am standing by produce, milk", "Produce", ["milk"]),
        ("starting at the bakery, milk", "Bakery", ["milk"]),
        ("near the produce, milk", "Produce", ["milk"]),
        ("from the bakery, milk", "Bakery", ["milk"]),
        ("i am at the bakery, i need milk and get me crayons", "Bakery", ["milk", "crayons"]),
    ],
)
def test_existing_forms_unchanged(dataset, settings, text, start, items):
    assert _parse(text, dataset, settings) == (start, items)


# ---------- negatives: not a start phrase ----------


@pytest.mark.parametrize(
    "text, items",
    [
        ("bread in a bag and milk", ["bread in a bag", "milk"]),
        ("milk at home, eggs", ["milk at home", "eggs"]),
        ("im at home, milk", ["im at home", "milk"]),  # 'home' is not a store zone
        ("produce, milk", ["produce", "milk"]),  # a zone name alone is not a start
    ],
)
def test_not_a_start_phrase(dataset, settings, text, items):
    assert _parse(text, dataset, settings) == (None, items)


def test_no_product_name_is_read_as_a_start_phrase(dataset, settings):
    wrong = []
    for p in dataset.products:
        start, items = _parse(p.name, dataset, settings)
        if start is not None or items != [p.name.lower()]:
            wrong.append((p.name, start, items))
    assert wrong == []


def test_suffix_words_come_from_config():
    import json

    data = json.loads((Path(__file__).resolve().parent.parent / "config" / "query_phrases.json").read_text(encoding="utf-8"))
    assert data["start_label_suffixes"] == ["section", "area", "zone", "department"]
