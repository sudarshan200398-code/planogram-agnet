"""LocalFilesProvider: stores listed in config/stores.json, each a folder of CSV/JSON files."""
from __future__ import annotations

import csv
import json
import math
import os
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from ..data_loader import load_dataset
from ..images import product_image
from ..validators import DataValidationError
from .base import StoreInfo, StoreNotFoundError

if TYPE_CHECKING:
    from ..data_loader import Dataset
    from ..images import ProductImage
    from ..settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STORES_FILE = REPO_ROOT / "config" / "stores.json"
STORES_FILE_ENV = "PLANOGRAM_STORES_FILE"
PRICES_FILE = "prices.csv"
_STORE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")

# The images module keeps one process-wide product lookup; guard it so two stores never share it.
_IMAGE_LOCK = threading.Lock()


def _read_registry(path: Path) -> dict[str, tuple[StoreInfo, Path]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    stores: dict[str, tuple[StoreInfo, Path]] = {}
    for entry in raw.get("stores", []):
        store_id = str(entry.get("id", ""))
        if not _STORE_ID.match(store_id):
            raise ValueError(f"stores registry {path}: bad store id {store_id!r} (lowercase letters, digits, '-')")
        if store_id in stores:
            raise ValueError(f"stores registry {path}: duplicate store id {store_id!r}")
        folder = Path(entry["data_dir"])
        if not folder.is_absolute():
            folder = path.resolve().parent.parent / folder  # relative to the repo root (config/..)
        stores[store_id] = (StoreInfo(id=store_id, name=str(entry["name"])), folder)
    if not stores:
        raise ValueError(f"stores registry {path}: no stores listed")
    return stores


def validate_prices(rows: list[dict[str, str]], header: list[str], skus: set[str]) -> list[str]:
    """Problems with a prices.csv: header, unknown or duplicate skus, non-numeric or negative prices."""
    if header != ["sku", "price"]:
        return [f"prices: header must be sku,price (got {','.join(header)})"]
    issues: list[str] = []
    seen: set[str] = set()
    for row in rows:
        sku, text = row["sku"], row["price"]
        if sku not in skus:
            issues.append(f"prices: unknown sku {sku}")
        if sku in seen:
            issues.append(f"prices: duplicate sku {sku}")
        seen.add(sku)
        try:
            value = float(text)
        except ValueError:
            issues.append(f"prices: sku {sku} price {text!r} is not a number")
            continue
        if not math.isfinite(value) or value < 0:
            issues.append(f"prices: sku {sku} price {text!r} must be zero or more")
    return issues


class LocalFilesProvider:
    """Reads each store from its folder through data_loader.load_dataset (validators always run)."""

    def __init__(self, stores_file: str | Path | None = None) -> None:
        path = Path(stores_file or os.environ.get(STORES_FILE_ENV) or DEFAULT_STORES_FILE)
        self._stores = _read_registry(path)

    def _folder(self, store_id: str) -> Path:
        try:
            return self._stores[store_id][1]
        except KeyError:
            raise StoreNotFoundError(store_id) from None

    def list_stores(self) -> list[StoreInfo]:
        return [info for info, _ in self._stores.values()]

    def load_dataset(self, store_id: str) -> Dataset:
        folder = self._folder(store_id)
        if not folder.is_dir():
            raise FileNotFoundError(f"store {store_id!r}: data folder not found")
        return load_dataset(folder, validate=True)

    def load_prices(self, store_id: str, dataset: Dataset) -> dict[str, float]:
        path = self._folder(store_id) / PRICES_FILE
        if not path.is_file():
            return {}
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            header = list(reader.fieldnames or [])
            rows = list(reader) if header == ["sku", "price"] else []
        issues = validate_prices(rows, header, {p.sku for p in dataset.products})
        if issues:
            raise DataValidationError(issues)
        return {row["sku"]: float(row["price"]) for row in rows}

    def product_image(self, store_id: str, sku: str, dataset: Dataset, settings: Settings) -> ProductImage:
        folder = self._folder(store_id)
        with _IMAGE_LOCK:
            return product_image(sku, dataset, folder, settings)
