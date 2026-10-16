"""Shared lookups for route handlers."""
from __future__ import annotations

from fastapi import Request

from planogram_agent.settings import Settings

from .engines import StoreEngine, StoreEngines


def engines_of(request: Request) -> StoreEngines:
    return request.app.state.engines


def settings_of(request: Request) -> Settings:
    return request.app.state.engines.settings


def engine_for(request: Request, store_id: str) -> StoreEngine:
    """The store's engine; ApiError 404 STORE_NOT_FOUND for an unknown id."""
    return engines_of(request).get(store_id)
