"""The store data interface. The API talks only to this, never to files or the company API directly."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel

if TYPE_CHECKING:
    from ..data_loader import Dataset
    from ..images import ProductImage
    from ..settings import Settings


class StoreInfo(BaseModel):
    """One store in the registry."""

    id: str
    name: str


class StoreNotFoundError(LookupError):
    """The store id is not in the registry."""


@runtime_checkable
class StoreDataProvider(Protocol):
    """Where store data comes from: local folders today, the company API later."""

    def list_stores(self) -> list[StoreInfo]:
        """Every store, in registry order."""
        ...

    def load_dataset(self, store_id: str) -> Dataset:
        """The store's validated map, products, planogram and inventory. Raises StoreNotFoundError."""
        ...

    def load_prices(self, store_id: str, dataset: Dataset) -> dict[str, float]:
        """Optional prices in rupees by sku; an empty mapping when the store has none."""
        ...

    def product_image(self, store_id: str, sku: str, dataset: Dataset, settings: Settings) -> ProductImage:
        """The product's picture: a real image if the store has one, else a generated placeholder."""
        ...
