"""One engine per store, built once from the provider and kept; each with its own lock.

The engine's clarification sessions live in memory inside each store's orchestrator, so run one worker
per instance (see api/README.md). Engine calls for a store run one at a time under that store's lock,
because the session store is not thread-safe.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from planogram_agent.data_loader import Dataset
from planogram_agent.interface import create_finder_for_dataset
from planogram_agent.providers import StoreDataProvider, StoreInfo, StoreNotFoundError
from planogram_agent.runtime.orchestrator import Orchestrator
from planogram_agent.schemas import Product
from planogram_agent.settings import Settings
from planogram_agent.validators import DataValidationError

from .errors import ApiError

logger = logging.getLogger("planogram_api")


@dataclass
class StoreEngine:
    info: StoreInfo
    dataset: Dataset
    finder: Orchestrator
    prices: dict[str, float]
    lock: threading.Lock = field(default_factory=threading.Lock)
    products: dict[str, Product] = field(default_factory=dict)
    inventory: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.products = {p.sku: p for p in self.dataset.products}
        self.inventory = {s.sku: s.quantity for s in self.dataset.inventory}

    def product(self, sku: str) -> Product:
        try:
            return self.products[sku]
        except KeyError:
            raise ApiError(404, "PRODUCT_NOT_FOUND", f"No product {sku!r} in store {self.info.id!r}") from None


class StoreEngines:
    def __init__(self, provider: StoreDataProvider, settings: Settings) -> None:
        self.provider = provider
        self.settings = settings
        self._infos = {s.id: s for s in provider.list_stores()}
        self._engines: dict[str, StoreEngine] = {}
        self._build_lock = threading.Lock()

    def store_ids(self) -> list[str]:
        return list(self._infos)

    def is_loaded(self, store_id: str) -> bool:
        return store_id in self._engines

    def get(self, store_id: str) -> StoreEngine:
        engine = self._engines.get(store_id)
        if engine is not None:
            return engine
        if store_id not in self._infos:
            raise ApiError(404, "STORE_NOT_FOUND", f"No store with id {store_id!r}")
        with self._build_lock:
            engine = self._engines.get(store_id)
            if engine is None:
                engine = self._build(store_id)
                self._engines[store_id] = engine
        return engine

    def _build(self, store_id: str) -> StoreEngine:
        try:
            dataset = self.provider.load_dataset(store_id)
            prices = self.provider.load_prices(store_id, dataset)
        except StoreNotFoundError:
            raise ApiError(404, "STORE_NOT_FOUND", f"No store with id {store_id!r}") from None
        except (DataValidationError, FileNotFoundError, ValueError) as exc:
            logger.error("store %s could not be loaded: %s", store_id, type(exc).__name__)
            raise ApiError(503, "STORE_UNAVAILABLE", f"Store {store_id!r} data could not be loaded") from None
        finder = create_finder_for_dataset(dataset, settings=self.settings)
        return StoreEngine(info=self._infos[store_id], dataset=dataset, finder=finder, prices=prices)
