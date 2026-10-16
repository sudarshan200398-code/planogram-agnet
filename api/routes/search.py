"""Search, clarification and basket routes. All engine calls for a store run under that store's lock."""
from __future__ import annotations

from fastapi import APIRouter, Request

from planogram_agent.basket import add_item, basket_finder_for, plan_basket, set_quantity
from planogram_agent.interface import answer_question, run_query

from .. import models, presenters
from ..deps import engine_for, settings_of
from ..errors import ApiError

router = APIRouter(tags=["search"])

_ERRORS = {422: {"model": models.ErrorBody}, 404: {"model": models.ErrorBody}}


@router.post("/stores/{store_id}/search", response_model=models.SearchResponse, responses=_ERRORS)
def search(store_id: str, body: models.SearchRequest, request: Request) -> models.SearchResponse:
    """The full request pipeline on typed text (start phrases, quantities, lists, typos)."""
    settings = settings_of(request)
    if len(body.text) > settings.max_query_chars:
        raise ApiError(422, "TEXT_TOO_LONG", f"text: must be at most {settings.max_query_chars} characters")
    if not body.text.strip():
        raise ApiError(422, "VALIDATION_ERROR", "text: must not be blank")
    e = engine_for(request, store_id)
    with e.lock:
        answer = run_query(e.finder, body.text.strip(), start=body.start, accessible_only=True if body.step_free else None)
        return presenters.search_response(e, answer)


@router.post("/stores/{store_id}/clarify", response_model=models.SearchResponse,
             responses={**_ERRORS, 409: {"model": models.ErrorBody}})
def clarify(store_id: str, body: models.ClarifyRequest, request: Request) -> models.SearchResponse:
    """Answer the pending question from /search or /basket/route with one of its offered skus."""
    e = engine_for(request, store_id)
    with e.lock:
        owner = next((f for f in (e.finder, basket_finder_for(e.finder)) if f.sessions.get(body.session_id)), None)
        if owner is None:
            raise ApiError(409, "SESSION_NOT_FOUND",
                           "This question has expired or belongs to another store or worker; search again")
        state = owner.sessions.get(body.session_id)
        question = next((q for q in state.pending_questions if q.item_index == body.item_index), None)
        if question is None or body.sku not in {o.sku for o in question.options}:
            raise ApiError(422, "INVALID_CHOICE", "item_index and sku must match a pending question and one of its options")
        answer = answer_question(owner, session_id=body.session_id, item_index=body.item_index, sku=body.sku)
        return presenters.search_response(e, answer)


@router.post("/stores/{store_id}/basket/route", response_model=models.SearchResponse, responses=_ERRORS)
def basket_route(store_id: str, body: models.BasketRouteRequest, request: Request) -> models.SearchResponse:
    """Route for a basket of skus, through the same pipeline as typed text, without the AI model."""
    settings = settings_of(request)
    if len(body.items) > settings.max_items:
        raise ApiError(422, "TOO_MANY_ITEMS", f"items: at most {settings.max_items} products")
    skus = [line.sku for line in body.items]
    if len(set(skus)) != len(skus):
        raise ApiError(422, "DUPLICATE_SKU", "items: each sku may appear once; use qty for more")
    for line in body.items:
        if not settings.basket_min_quantity <= line.qty <= settings.basket_max_quantity:
            raise ApiError(422, "QUANTITY_OUT_OF_RANGE",
                           f"qty: must be {settings.basket_min_quantity} to {settings.basket_max_quantity}")
    e = engine_for(request, store_id)
    basket: dict = {}
    for line in body.items:
        product = e.product(line.sku)
        result = add_item(basket, product.sku, product.name, settings)
        if not result.ok:
            raise ApiError(422, "BASKET_TOO_LONG", result.message)
        set_quantity(basket, product.sku, line.qty, settings)
    with e.lock:
        answer = plan_basket(e.finder, basket, start=body.start, accessible_only=True if body.step_free else None)
        return presenters.search_response(e, answer)
