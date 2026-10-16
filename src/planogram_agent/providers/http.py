"""HttpProvider: a stub for the company's store API. Same interface as LocalFilesProvider; not wired in.

Nothing here is called today. It documents what we expect the company API to offer so the swap is a
configuration change, not a rewrite of the API layer.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import StoreInfo

if TYPE_CHECKING:
    from ..data_loader import Dataset
    from ..images import ProductImage
    from ..settings import Settings

_TODO = "HttpProvider is a stub until the company API is available; use LocalFilesProvider."


class HttpProvider:
    """Store data from the company API (expected endpoints; all JSON unless noted):

    GET {base_url}/stores                       -> [{id, name}]
    GET {base_url}/stores/{id}/map              -> graph.json shape: floors, bounds, nodes, edges, connectors
    GET {base_url}/stores/{id}/products         -> [{sku, name, brand, category, size, keywords[]}]
    GET {base_url}/stores/{id}/planogram        -> [{sku, floor, zone, bay, shelf_level, position, node_id}]
    GET {base_url}/stores/{id}/inventory        -> [{sku, quantity}]
    GET {base_url}/stores/{id}/prices           -> [{sku, price}] in rupees (optional; 404 means none)
    GET {base_url}/stores/{id}/images/{sku}     -> image bytes (optional; 404 means use the placeholder)

    Rules for the real implementation:
    - Build pydantic models from the responses and run the same validators as data_loader.load_dataset,
      so bad company data fails loudly instead of producing wrong routes.
    - Read the API key from the environment variable named by api_key_env at call time; never log it,
      never put it in URLs, and send it only to base_url.
    - Time out every call and cache datasets per store; the API layer already caches engines per store.
    """

    def __init__(self, base_url: str, api_key_env: str = "COMPANY_API_KEY", timeout_seconds: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env  # the variable's name only, never its value
        self.timeout_seconds = timeout_seconds

    def list_stores(self) -> list[StoreInfo]:
        raise NotImplementedError(_TODO)

    def load_dataset(self, store_id: str) -> Dataset:
        raise NotImplementedError(_TODO)

    def load_prices(self, store_id: str, dataset: Dataset) -> dict[str, float]:
        raise NotImplementedError(_TODO)

    def product_image(self, store_id: str, sku: str, dataset: Dataset, settings: Settings) -> ProductImage:
        raise NotImplementedError(_TODO)
