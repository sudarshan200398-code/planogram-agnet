"""Write a synthetic prices.csv (sku, price in rupees) for a store's products.csv.

Prices are made up. Each price depends only on the product's sku and category (through a hash),
so the output is the same on every run and does not depend on row order.

Usage (PowerShell, from the repo root):
    python scripts/generate_store_prices.py --products data/store_demo/products.csv --out data/store_demo/prices.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path


def _unit(text: str) -> float:
    """A stable number in [0, 1) from text."""
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16) / 16**12


def price_for(sku: str, category: str) -> str:
    """Rupee price as text with two decimals: a band per category, spread per sku, rounded to 0.50."""
    band = 20 + round(_unit("category:" + category.lower()) * 30) * 10  # 20 .. 320 rupees
    value = band * (0.6 + 1.9 * _unit("sku:" + sku))
    return f"{max(5.0, round(value * 2) / 2):.2f}"


def write_prices(products_csv: Path, out_csv: Path) -> int:
    """Write prices for every product in products_csv; returns the number of rows written."""
    with open(products_csv, newline="", encoding="utf-8") as f:
        products = list(csv.DictReader(f))
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["sku", "price"])
        for p in products:
            writer.writerow([p["sku"], price_for(p["sku"], p["category"])])
    return len(products)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--products", type=Path, default=Path("data/store_demo/products.csv"))
    parser.add_argument("--out", type=Path, default=Path("data/store_demo/prices.csv"))
    args = parser.parse_args()
    print(f"wrote {write_prices(args.products, args.out)} prices to {args.out}")


if __name__ == "__main__":
    main()
