"""Categories, product browsing, suggestions, product detail and product pictures."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from planogram_agent.autocomplete import suggest

from .. import models, presenters
from ..deps import engine_for, engines_of, settings_of
from ..errors import ApiError

router = APIRouter(tags=["catalogue"])


@router.get("/stores/{store_id}/categories", response_model=models.CategoriesResponse)
def categories(store_id: str, request: Request) -> models.CategoriesResponse:
    e = engine_for(request, store_id)
    counts: dict[str, int] = {}
    for p in e.dataset.products:
        counts[p.category] = counts.get(p.category, 0) + 1
    return models.CategoriesResponse(
        store_id=store_id,
        categories=[models.Category(name=c, product_count=counts[c]) for c in sorted(counts, key=str.casefold)],
    )


@router.get("/stores/{store_id}/products", response_model=models.ProductPage)
def browse(
    store_id: str,
    request: Request,
    category: str | None = Query(default=None, max_length=100, description="Exact category name (any case)"),
    page: int = Query(default=1, ge=1),
    page_size: int | None = Query(default=None, ge=1, description="Default api_page_size_default, at most api_page_size_max"),
) -> models.ProductPage:
    settings = settings_of(request)
    size = page_size or settings.api_page_size_default
    if size > settings.api_page_size_max:
        raise ApiError(422, "VALIDATION_ERROR", f"page_size: must be at most {settings.api_page_size_max}")
    e = engine_for(request, store_id)
    products = e.dataset.products
    name = None
    if category is not None:
        name = next((p.category for p in products if p.category.casefold() == category.casefold()), None)
        if name is None:
            raise ApiError(404, "CATEGORY_NOT_FOUND", f"No category {category!r} in store {store_id!r}")
        products = [p for p in products if p.category == name]
    ordered = sorted(products, key=lambda p: (p.name.casefold(), p.sku))  # stable across requests
    chunk = ordered[(page - 1) * size: page * size]
    return models.ProductPage(
        store_id=store_id, category=name, page=page, page_size=size, total=len(ordered),
        pages=presenters.page_count(len(ordered), size), items=[presenters.product(e, p.sku) for p in chunk],
    )


@router.get("/stores/{store_id}/suggest", response_model=models.SuggestResponse)
def suggestions(store_id: str, request: Request, q: str = Query(default="")) -> models.SuggestResponse:
    settings = settings_of(request)
    if len(q) > settings.max_query_chars:
        raise ApiError(422, "TEXT_TOO_LONG", f"q: must be at most {settings.max_query_chars} characters")
    e = engine_for(request, store_id)
    with e.lock:
        rows = suggest(q, e.dataset, settings)
    return models.SuggestResponse(store_id=store_id, suggestions=[presenters.suggestion(e, s) for s in rows])


@router.get("/stores/{store_id}/products/{sku}", response_model=models.Product)
def product_detail(store_id: str, sku: str, request: Request) -> models.Product:
    e = engine_for(request, store_id)
    e.product(sku)
    return presenters.product(e, sku)


@router.get(
    "/stores/{store_id}/products/{sku}/image",
    response_class=Response,
    responses={200: {"content": {"image/png": {}, "image/svg+xml": {}}}, 404: {"model": models.ErrorBody}},
)
def product_picture(store_id: str, sku: str, request: Request) -> Response:
    e = engine_for(request, store_id)
    e.product(sku)
    img = engines_of(request).provider.product_image(store_id, sku, e.dataset, settings_of(request))
    data = img.data.encode("utf-8") if isinstance(img.data, str) else img.data
    return Response(content=data, media_type=img.mime, headers={"Cache-Control": "public, max-age=3600"})
