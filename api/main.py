"""FastAPI app for the store product finder. Run: uvicorn api.main:app --workers 1 (see api/README.md)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from planogram_agent.providers import LocalFilesProvider, StoreDataProvider
from planogram_agent.settings import Settings, load_settings

from .engines import StoreEngines
from .errors import install_error_handlers
from .middleware import SlidingWindowLimiter, install_middleware
from .routes import catalog_router, search_router, stores_router
from .settings import cors_origins

DESCRIPTION = """Find products in a store, check stock, and get the shortest walking route across floors.

Every store endpoint is under `/stores/{store_id}`. Errors always have the body
`{"error": {"code", "message", "request_id"}}`; send `X-Request-ID` to correlate logs.
Clarification sessions are kept in memory: run one worker per instance.
"""


def create_app(provider: StoreDataProvider | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="Store Product Finder API", version="2.0.0-phase1", description=DESCRIPTION)
    app.state.engines = StoreEngines(provider or LocalFilesProvider(), settings)

    install_error_handlers(app)
    install_middleware(app, SlidingWindowLimiter(settings.api_rate_limit_per_minute))
    origins = cors_origins()
    if origins:  # added last so it wraps everything, including rate-limit and error responses
        app.add_middleware(
            CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Request-ID"], expose_headers=["X-Request-ID", "Retry-After"],
        )

    app.include_router(stores_router)
    app.include_router(catalog_router)
    app.include_router(search_router)
    return app


app = create_app()
