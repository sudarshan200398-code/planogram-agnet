"""Synthetic prices from product rules (config/price_ranges.json): ranges, retail endings, pack sizes,
rule order, coverage, reproducibility and India sanity limits."""
from __future__ import annotations

import csv
import importlib.util
import itertools
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RULES_FILE = ROOT / "config" / "price_ranges.json"
STORES = {"central": ROOT / "data" / "store_demo", "riverside": ROOT / "data" / "store_riverside"}


def _module():
    spec = importlib.util.spec_from_file_location("generate_store_prices", ROOT / "scripts" / "generate_store_prices.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pricing():
    return _module()


@pytest.fixture(scope="module")
def rules(pricing):
    return pricing.load_rules(RULES_FILE)


@pytest.fixture(scope="module")
def priced(pricing, rules):
    """store -> list of PriceResult for every product, computed from the store folder."""
    return {store: pricing.price_store(folder, rules) for store, folder in STORES.items()}


def _csv_prices(folder: Path) -> dict[str, str]:
    with open(folder / "prices.csv", newline="", encoding="utf-8") as f:
        return {r["sku"]: r["price"] for r in csv.DictReader(f)}


# ---------- the rules file ----------


def test_rules_file_is_consistent(rules):
    types = [r["type"] for r in rules["rules"]]
    assert len(types) == len(set(types))
    for rule in rules["rules"]:
        assert rule["match"] and all(t == t.lower().strip() for t in rule["match"]), rule["type"]
        assert rule["group"] in rules["groups"], rule["type"]
        for band in rule.get("bands", []):
            assert 0 < band["min"] < band["max"], rule["type"]
        # one band per size dimension, so every size of a product scales from the same reference
        dims = [band["_size"].dim if band.get("_size") else "none" for band in rule.get("bands", [])]
        assert len(dims) == len(set(dims)), (rule["type"], dims)
    for zone, band in rules["zone_fallbacks"].items():
        assert 0 < band["min"] < band["max"] and band["group"] in rules["groups"], zone


def test_every_zone_of_both_stores_has_a_fallback(rules):
    for folder in STORES.values():
        with open(folder / "planogram.csv", newline="", encoding="utf-8") as f:
            zones = {r["zone"] for r in csv.DictReader(f)}
        assert zones <= set(rules["zone_fallbacks"]), zones - set(rules["zone_fallbacks"])


def test_specific_rules_come_before_general_rules_in_the_file(pricing, rules):
    """No term of a later rule may contain a term of an earlier rule (e.g. 'rice' before 'rice cooker')."""
    problems = []
    for (i, earlier), (j, later) in itertools.combinations(enumerate(rules["rules"]), 2):
        for general, specific in itertools.product(earlier["match"], later["match"]):
            if pricing.term_contains(specific, general):
                problems.append(f"{later['type']!r} ({specific!r}) must come before {earlier['type']!r} ({general!r})")
    assert problems == []


# ---------- every product ----------


@pytest.mark.parametrize("store", STORES)
def test_every_sku_has_exactly_one_price(store, priced):
    with open(STORES[store] / "products.csv", newline="", encoding="utf-8") as f:
        skus = [r["sku"] for r in csv.DictReader(f)]
    prices = _csv_prices(STORES[store])
    assert set(prices) == set(skus) and len(prices) == len(skus)
    assert [r.sku for r in priced[store]] == skus
    assert {r.sku: f"{r.price:.2f}" for r in priced[store]} == prices


@pytest.mark.parametrize("store", STORES)
def test_no_product_priced_by_a_general_rule_when_a_specific_rule_matches(store, pricing, rules, priced):
    wrong = []
    for r in priced[store]:
        if r.source != "rule":
            continue
        for other_type, other_terms in r.all_matches.items():
            if other_type == r.rule_type:
                continue
            for mine, theirs in itertools.product(r.matched_terms, other_terms):
                if pricing.term_contains(theirs, mine):
                    wrong.append(f"{r.name}: {r.rule_type!r} ({mine!r}) but {other_type!r} ({theirs!r}) is more specific")
    assert wrong == []


@pytest.mark.parametrize("store", STORES)
def test_every_price_is_inside_its_range(store, pricing, priced):
    for r in priced[store]:
        if r.source == "face_value":
            assert r.price == r.size_quantity, r.name
            continue
        low = pricing.retail_round(r.band_min * r.factor)
        high = pricing.retail_round(r.band_max * r.factor)
        assert low <= r.price <= high, (r.name, r.price, low, high)


@pytest.mark.parametrize("store", STORES)
def test_retail_endings(store, priced):
    for r in priced[store]:
        p = r.price
        assert p == int(p), r.name
        if r.source == "face_value":
            continue
        if p < 100:
            assert p >= 1
        elif p < 1000:
            assert int(p) % 10 == 9, (r.name, p)
        else:
            assert int(p) % 100 == 99, (r.name, p)


def test_retail_round_is_monotonic_across_band_edges(pricing):
    xs = [x / 4 for x in range(1, 4 * 2500)]
    rounded = [pricing.retail_round(x) for x in xs]
    assert rounded == sorted(rounded)
    assert (pricing.retail_round(99.99), pricing.retail_round(100.0), pricing.retail_round(130.0)) == (99, 109, 139)
    assert (pricing.retail_round(999.99), pricing.retail_round(1000.0), pricing.retail_round(1250.0)) == (999, 1099, 1299)


@pytest.mark.parametrize("store", STORES)
def test_bigger_pack_never_costs_less(store, pricing, priced, capsys):
    families: dict[str, list] = {}
    for r in priced[store]:
        families.setdefault(r.family, []).append(r)
    compared = mixed = 0
    for members in families.values():
        for a, b in itertools.combinations(members, 2):
            order = pricing.compare_sizes(a.size, b.size)
            if order is None:
                mixed += 1
                continue
            compared += 1
            bigger, smaller = (a, b) if order > 0 else (b, a)
            if order != 0:
                assert bigger.price >= smaller.price, (bigger.name, bigger.price, smaller.name, smaller.price)
    with capsys.disabled():
        print(f"\n[{store}] same-product size pairs compared: {compared}, mixed-unit pairs reported: {mixed}")
    assert compared > 0 or store == "central"


@pytest.mark.parametrize("store", STORES)
def test_coverage_report_adds_up(store, pricing, priced):
    report = pricing.coverage_report(priced[store])
    assert sum(report["rules"].values()) + sum(report["fallbacks"].values()) + report["face_value"] == len(priced[store])


# ---------- matching ----------


EXPECTED_TYPES = {
    "Butter Croissants": "pastries", "Rice Cooker": "kitchen appliances", "Rice Noodles": "pasta and noodles",
    "Peanut Butter": "peanut butter", "Coconut Milk": "coconut milk", "Chocolate Milk": "chocolate milk",
    "Milk Chocolate Bar": "chocolate bar", "Chicken Curry": "frozen and ready meals", "Chicken Sausages": "deli meats",
    "Chicken Roll": "deli meats", "Turkey Mince": "fresh meat", "Roast Beef": "deli meats",
    "Chicken Mince": "chicken", "Cheese Crackers": "crisps and savoury snacks", "Cheese Puffs": "crisps and savoury snacks",
    "Cream Cheese": "cheese", "Fish Pie": "frozen and ready meals", "Apple Pie": "pies and tarts",
    "Apple Juice": "juice and smoothies", "Mango Pickle": "sauces and condiments", "Dried Mango": "nuts and dried fruit",
    "Tortilla Chips": "crisps and savoury snacks", "Flour Tortillas": "bread", "Brownie Mix": "flour and baking",
    "Brownie Bites": "sweet bakery", "Still Water Bottle": "water", "Butternut Squash": "staple vegetables",
    "Orange Squash": "soft drinks", "Mustard Oil": "cooking oils", "Masala Chai": "tea and coffee",
    "Rohu Steaks": "fish and seafood", "Lamb Chops": "lamb and mutton", "Tuna Cat Pouch": "pet food and care",
    "Diaper Rash Cream": "health and baby care", "Garden Slide": "big toys", "Cough Sweets": "pharmacy small items",
    "Hot Chocolate Tin": "hot chocolate", "Mixed Vegetables": "frozen vegetables", "Coffee Creamer": "cream",
    "Coffee Maker": "kitchen appliances", "Gift Wrap Roll": "gift wrap and store supplies",
    "Receipt Rolls": "gift wrap and store supplies", "Breakfast Sandwiches": "frozen and ready meals",
    "Chicken Sandwich": "sandwiches and wraps", "White Sandwich Bread": "bread", "Roasted Chickpeas": "crisps and savoury snacks",
    "Puzzle Book": "magazines and books", "Jigsaw Puzzle": "toys", "Veg Puff": "pastries", "Cinnamon Rolls": "pastries",
    "Veg Spring Rolls": "frozen and ready meals", "Pressure Cooker": "cookware", "Gift Voucher": "gift card",
}


def test_tricky_names_get_the_right_type(priced):
    by_name = {r.name: r.rule_type for rs in priced.values() for r in rs}
    for fragment, expected in EXPECTED_TYPES.items():
        hits = {name: t for name, t in by_name.items() if fragment in name}
        assert hits, f"no product contains {fragment!r}"
        assert set(hits.values()) == {expected}, (fragment, hits)
    water_bottle = {t for name, t in by_name.items() if "Water Bottle" in name and "Still" not in name}
    assert water_bottle == {"travel small accessories"}  # a reusable bottle, not a drink


def test_category_text_is_ignored(pricing, rules):
    product = {"sku": "X-1", "name": "Store Brand Garden Slide large", "brand": "Store Brand",
               "category": "Milk & plant-based beverages", "size": "large",
               "keywords": "garden slide|slide|milk & plant-based beverages"}
    assert pricing.price_product(product, "Toys & Stationery", rules).rule_type == "big toys"


def test_no_rule_and_no_zone_fallback_fails_loudly(pricing, rules):
    product = {"sku": "ODD-001", "name": "Acme Flux Capacitor standard", "brand": "Acme", "category": "Gadgets",
               "size": "standard", "keywords": "flux capacitor"}
    with pytest.raises(pricing.PricingError, match="ODD-001"):
        pricing.price_products([product], {"ODD-001": "Nowhere Zone"}, rules)


# ---------- India sanity ----------


@pytest.mark.parametrize("store", STORES)
def test_prices_look_right_for_india(store, rules, priced):
    sanity = rules["sanity"]
    problems = []
    for r in priced[store]:
        if r.group == "grocery" and r.price > sanity["grocery_max"]:
            problems.append(f"grocery above {sanity['grocery_max']}: {r.name} {r.price}")
        if r.price < sanity["min_price"] and r.rule_type not in sanity["low_price_ok"] and r.source != "face_value":
            problems.append(f"below {sanity['min_price']}: {r.name} {r.price}")
    assert problems == []


# ---------- reproducible ----------


@pytest.mark.parametrize("store", STORES)
def test_prices_are_reproducible_and_match_the_committed_files(store, pricing, tmp_path):
    folder = STORES[store]
    for out in ("a.csv", "b.csv"):
        pricing.write_prices(folder / "products.csv", tmp_path / out)
    a, b = (tmp_path / "a.csv").read_bytes(), (tmp_path / "b.csv").read_bytes()
    assert a == b
    assert a == (folder / "prices.csv").read_bytes().replace(b"\r\n", b"\n")


def test_rules_file_is_valid_json():
    json.loads(RULES_FILE.read_text(encoding="utf-8"))
