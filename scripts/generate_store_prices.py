"""Write a synthetic prices.csv (sku, price in rupees) for a store from the rules in config/price_ranges.json.

Prices are made up. A product's price comes from the first rule whose words appear in its name or
keywords (never its category text), scaled by its pack size and rounded to retail endings. Products
no rule matches use their zone's fallback band; a product with neither stops the run with an error.
All sizes of one product share a position in the band, so a bigger pack never costs less.
The output depends only on the product text and the rules: the same files on every run.

Usage (PowerShell, from the repo root):
    python scripts/generate_store_prices.py                         # both stores, with a coverage report
    python scripts/generate_store_prices.py --products data/store_demo/products.csv --out data/store_demo/prices.csv
"""
# No `from __future__ import annotations`: the tests load this file with importlib, and dataclasses
# with string annotations need the module registered in sys.modules.
import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULES = ROOT / "config" / "price_ranges.json"
STORE_FOLDERS = {"central": ROOT / "data" / "store_demo", "riverside": ROOT / "data" / "store_riverside"}

_QUANTITY = re.compile(r"^(\d+(?:\.\d+)?)\s*(g|kg|ml|l|pack|value|sheets|inch|piece|head|bunch|slice|whole)$")
_UNIT_DIM = {"g": ("mass", 1), "kg": ("mass", 1000), "ml": ("volume", 1), "l": ("volume", 1000),
             "pack": ("count", 1), "piece": ("count", 1), "head": ("count", 1), "bunch": ("count", 1),
             "sheets": ("sheets", 1), "inch": ("inch", 1), "value": ("value", 1)}
QUANTITY_DIMS = {"mass", "volume", "count", "sheets", "inch"}


class PricingError(Exception):
    """Products that no rule and no zone fallback can price."""


@dataclass(frozen=True)
class Size:
    dim: str  # mass, volume, count, sheets, inch, value, grade or unknown
    quantity: float = 0.0
    grade: str = ""


@dataclass
class PriceResult:
    sku: str
    name: str
    family: str
    size: str
    size_quantity: float
    price: float
    rule_type: str
    group: str
    source: str  # rule, fallback or face_value
    band_min: float
    band_max: float
    factor: float
    scaled: bool
    matched_terms: list[str] = field(default_factory=list)
    all_matches: dict[str, list[str]] = field(default_factory=dict)


# ---------- rules ----------


def _words(term: str) -> list[str]:
    return [w for w in re.split(r"[\s\-]+", term.lower()) if w]


def _singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("oes"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def term_contains(specific: str, general: str) -> bool:
    """True if `specific` strictly contains `general` as whole words (plurals ignored), e.g. rice cooker > rice."""
    s = [_singular(w) for w in _words(specific)]
    g = [_singular(w) for w in _words(general)]
    if s == g or len(g) >= len(s):
        return False
    return any(s[i:i + len(g)] == g for i in range(len(s) - len(g) + 1))


def _term_pattern(term: str) -> re.Pattern:
    body = r"[\s\-]+".join(re.escape(w) for w in _words(term))
    return re.compile(r"(?<![a-z0-9])" + body + r"(?:s|es)?(?![a-z0-9])")


def load_rules(path: str | Path = DEFAULT_RULES) -> dict:
    rules = json.loads(Path(path).read_text(encoding="utf-8"))
    for rule in rules["rules"]:
        rule["_patterns"] = [(t, _term_pattern(t)) for t in rule["match"]]
        for band in rule.get("bands", []):
            band["_size"] = parse_size(band["ref"], rules) if band.get("ref") else None
    return rules


# ---------- sizes and rounding ----------


def parse_size(text: str | None, rules: dict) -> Size:
    t = (text or "").strip().lower()
    m = _QUANTITY.match(t)
    if m:
        qty, unit = float(m.group(1)), m.group(2)
        if unit in ("slice", "whole"):
            return Size("grade", grade=unit)
        dim, mult = _UNIT_DIM[unit]
        return Size(dim, qty * mult)
    if t == "single":
        return Size("count", 1.0)
    if t.startswith("uk "):
        return Size("grade", grade="uk")
    if t in rules["grade_factors"]:
        return Size("grade", grade=t)
    return Size("unknown")


def compare_sizes(a: str, b: str, rules: dict | None = None) -> int | None:
    """+1 if size a is bigger, -1 if smaller, 0 if equal, None if they cannot be compared (mixed units)."""
    rules = rules or load_rules()
    sa, sb = parse_size(a, rules), parse_size(b, rules)
    if sa.dim in QUANTITY_DIMS and sa.dim == sb.dim:
        return (sa.quantity > sb.quantity) - (sa.quantity < sb.quantity)
    if sa.dim == sb.dim == "grade":
        fa, fb = rules["grade_factors"][sa.grade], rules["grade_factors"][sb.grade]
        return (fa > fb) - (fa < fb)
    return None


def retail_round(value: float) -> float:
    """Whole rupees under 100, endings in 9 up to 999, endings in 99 from 1,000. Never decreases as value grows."""
    if value < 100:
        return float(max(1, math.floor(value)))
    if value < 1000:
        return float(math.floor(value / 10) * 10 + 9)
    return float(math.floor(value / 100) * 100 + 99)


def _unit(text: str) -> float:
    """A stable number in [0, 1) from text."""
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16) / 16**12


# ---------- pricing ----------


def _family(product: dict) -> str:
    name, size = product["name"], (product.get("size") or "").strip()
    base = name[: -len(size)].strip() if size and name.endswith(size) else name
    return f"{(product.get('brand') or '').lower()}|{base.lower()}"


def _match_text(product: dict) -> str:
    category = (product.get("category") or "").strip().lower()
    keywords = [k for k in (product.get("keywords") or "").split("|") if k and k.strip().lower() != category]
    return " | ".join([product["name"], *keywords]).lower()


def _matches(text: str, rules: dict) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for rule in rules["rules"]:
        terms = [t for t, pattern in rule["_patterns"] if pattern.search(text)]
        if terms:
            found[rule["type"]] = terms
    return found


def _band_and_factor(bands: list[dict], size: Size, rules: dict) -> tuple[dict, float, bool]:
    low, high = rules["size_factor_limits"]
    if size.dim in QUANTITY_DIMS:
        for band in bands:
            ref = band.get("_size")
            if ref is not None and ref.dim == size.dim:
                factor = min(high, max(low, (size.quantity / ref.quantity) ** rules["size_exponent"]))
                return band, factor, True
    null_band = next((b for b in bands if not b.get("ref")), None)
    if size.dim == "grade":
        return (null_band or bands[0]), rules["grade_factors"][size.grade], True
    return (null_band or bands[0]), 1.0, False


def price_product(product: dict, zone: str | None, rules: dict) -> PriceResult:
    size = parse_size(product.get("size"), rules)
    all_matches = _matches(_match_text(product), rules)
    rule = next((r for r in rules["rules"] if r["type"] in all_matches), None)
    common = {"sku": product["sku"], "name": product["name"], "family": _family(product),
              "size": product.get("size") or "", "size_quantity": size.quantity, "all_matches": all_matches}

    if rule is not None and rule.get("face_value") and size.dim == "value":
        return PriceResult(**common, price=float(size.quantity), rule_type=rule["type"], group=rule["group"],
                           source="face_value", band_min=size.quantity, band_max=size.quantity, factor=1.0,
                           scaled=True, matched_terms=all_matches[rule["type"]])
    if rule is not None:
        band, factor, scaled = _band_and_factor(rule["bands"], size, rules)
        rule_type, group, source, matched = rule["type"], rule["group"], "rule", all_matches[rule["type"]]
    elif zone in rules["zone_fallbacks"]:
        band = rules["zone_fallbacks"][zone]
        factor = rules["grade_factors"][size.grade] if size.dim == "grade" else 1.0
        scaled = size.dim == "grade"
        rule_type, group, source, matched = f"fallback: {zone}", band["group"], "fallback", []
    else:
        raise PricingError(f"no price rule or zone fallback for: {product['sku']} {product['name']!r} (zone {zone!r})")

    position = _unit("family:" + common["family"])  # same for every size of the product
    raw = (band["min"] + (band["max"] - band["min"]) * position) * factor
    return PriceResult(**common, price=retail_round(raw), rule_type=rule_type, group=group, source=source,
                       band_min=band["min"], band_max=band["max"], factor=factor, scaled=scaled, matched_terms=matched)


def price_products(products: list[dict], zone_by_sku: dict[str, str], rules: dict) -> list[PriceResult]:
    results, missing = [], []
    for p in products:
        try:
            results.append(price_product(p, zone_by_sku.get(p["sku"]), rules))
        except PricingError:
            missing.append(p["sku"])
    if missing:
        raise PricingError(f"no price rule or zone fallback for {len(missing)} product(s): {', '.join(missing)}")
    return results


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def price_store(folder: str | Path, rules: dict) -> list[PriceResult]:
    folder = Path(folder)
    zone_by_sku: dict[str, str] = {}
    for row in _read_csv(folder / "planogram.csv"):
        zone_by_sku.setdefault(row["sku"], row["zone"])  # the first placement decides the fallback zone
    return price_products(_read_csv(folder / "products.csv"), zone_by_sku, rules)


def coverage_report(results: list[PriceResult]) -> dict:
    return {
        "rules": dict(Counter(r.rule_type for r in results if r.source == "rule")),
        "fallbacks": dict(Counter(r.rule_type.removeprefix("fallback: ") for r in results if r.source == "fallback")),
        "face_value": sum(r.source == "face_value" for r in results),
        "not_size_scaled": sum(not r.scaled for r in results),
    }


def write_prices(products_csv: Path, out_csv: Path, rules_path: str | Path = DEFAULT_RULES) -> list[PriceResult]:
    """Price every product in products_csv (planogram.csv beside it gives zones) and write out_csv."""
    results = price_store(Path(products_csv).parent, load_rules(rules_path))
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["sku", "price"])
        for r in results:
            writer.writerow([r.sku, f"{r.price:.2f}"])
    return results


def _print_report(store: str, results: list[PriceResult]) -> None:
    report = coverage_report(results)
    print(f"{store}: {len(results)} products, {report['face_value']} at face value, "
          f"{sum(report['fallbacks'].values())} on zone fallbacks, {report['not_size_scaled']} not size-scaled")
    for rule_type, n in sorted(report["rules"].items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  rule {rule_type}: {n}")
    for zone, n in sorted(report["fallbacks"].items()):
        print(f"  fallback {zone}: {n}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Write synthetic prices.csv files from config/price_ranges.json.")
    parser.add_argument("--products", type=Path, help="one store's products.csv (default: both stores)")
    parser.add_argument("--out", type=Path, help="where to write that store's prices.csv")
    args = parser.parse_args()
    if args.products:
        out = args.out or args.products.parent / "prices.csv"
        _print_report(str(args.products.parent), write_prices(args.products, out))
        return
    for store, folder in STORE_FOLDERS.items():
        _print_report(store, write_prices(folder / "products.csv", folder / "prices.csv"))


if __name__ == "__main__":
    main()
