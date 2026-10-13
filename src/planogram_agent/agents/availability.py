"""Deterministic availability agent checking stock levels and quantities."""
from __future__ import annotations

import weakref
from typing import Literal

from pydantic import BaseModel, Field

from ..data_loader import Dataset
from ..tools import check_inventory


class Availability(BaseModel):
    """Inventory availability status for a product SKU."""

    sku: str
    status: Literal["available", "unavailable", "unknown"]
    quantity: int = Field(default=0, ge=0)
    reason: str | None = None


_INVENTORY_QTY_CACHE: dict[int, tuple[weakref.ref[Dataset], dict[str, int]]] = {}


def _get_inventory_map(dataset: Dataset) -> dict[str, int]:
    """Return or build an in-memory SKU -> quantity map cached by dataset instance."""
    ds_id = id(dataset)
    if ds_id in _INVENTORY_QTY_CACHE:
        stored_ref, qty_map = _INVENTORY_QTY_CACHE[ds_id]
        if stored_ref() is dataset:
            return qty_map

    qty_map = {item.sku: item.quantity for item in dataset.inventory}

    def _cleanup(_ref: weakref.ref, key: int = ds_id) -> None:
        _INVENTORY_QTY_CACHE.pop(key, None)

    _INVENTORY_QTY_CACHE[ds_id] = (weakref.ref(dataset, _cleanup), qty_map)
    return qty_map


def clear_inventory_cache(dataset: Dataset | None = None) -> None:
    """Clear cached inventory map for a dataset or all datasets if None."""
    if dataset is None:
        _INVENTORY_QTY_CACHE.clear()
    else:
        _INVENTORY_QTY_CACHE.pop(id(dataset), None)


def check_availability(sku: str, dataset: Dataset) -> Availability:
    """Check availability for a SKU, adding quantity and reason to check_inventory.

    Status is determined by check_inventory. Fast dictionary lookup retrieves quantity.
    """
    status = check_inventory(sku, dataset)
    qty_map = _get_inventory_map(dataset)
    quantity = qty_map.get(sku, 0)

    reason: str | None = None
    if status == "available":
        reason = None
    elif status == "unavailable":
        reason = "Out of stock"
    elif status == "unknown":
        reason = f"SKU '{sku}' not found in store inventory data"

    return Availability(
        sku=sku,
        status=status,
        quantity=quantity,
        reason=reason,
    )
