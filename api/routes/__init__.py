"""API routers."""
from .catalog import router as catalog_router
from .search import router as search_router
from .stores import router as stores_router

__all__ = ["catalog_router", "search_router", "stores_router"]
