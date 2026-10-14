"""Public interface for store product finding and question answering."""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from .data_loader import load_dataset
from .llm.factory import make_client
from .llm.no_model import NoModelClient
from .runtime.orchestrator import Orchestrator
from .settings import Settings, load_settings

if TYPE_CHECKING:
    from .llm.base import LLMClient
    from .runtime.state import Answer


def create_finder(
    store_path: str | Path,
    settings: Settings | None = None,
    client: LLMClient | None = None,
) -> Orchestrator:
    """Load dataset and instantiate an Orchestrator.

    Supports the PLANOGRAM_PROVIDER environment variable override.
    Accepted values: 'none', 'gemini', 'fake'.
    An unknown value uses NoModelClient and sets finder.model_note to say so;
    it never crashes.

    If no client is given and provider is 'gemini' but GEMINI_API_KEY is missing,
    uses NoModelClient and notes it in finder.model_note. Never crashes.
    """
    if settings is None:
        settings = load_settings()

    dataset = load_dataset(store_path, validate=True)
    model_note: str | None = None

    env_provider = os.environ.get("PLANOGRAM_PROVIDER")
    if env_provider is not None:
        prov = env_provider.lower().strip()
        if prov in ("none", "gemini", "fake"):
            settings = settings.model_copy(update={"provider": prov})
        else:
            client = NoModelClient()
            model_note = f"Unknown PLANOGRAM_PROVIDER '{env_provider}'; using NoModelClient fallback"

    if client is None:
        provider_name = settings.provider.lower().strip()
        if provider_name == "none":
            client = NoModelClient()
            model_note = model_note or "Provider is 'none'; using NoModelClient"
        elif provider_name == "gemini" and not os.environ.get("GEMINI_API_KEY"):
            client = NoModelClient()
            model_note = model_note or "GEMINI_API_KEY missing in environment; using NoModelClient fallback"
        elif provider_name not in ("gemini", "fake", "none"):
            client = NoModelClient()
            model_note = model_note or f"Unknown provider '{settings.provider}'; using NoModelClient fallback"
        else:
            try:
                client = make_client(settings=settings)
            except Exception as e:  # noqa: BLE001
                client = NoModelClient()
                model_note = model_note or f"Client creation failed ({e}); using NoModelClient fallback"

    return Orchestrator(
        dataset=dataset,
        settings=settings,
        client=client,
        model_note=model_note,
    )


def run_query(
    finder: Orchestrator,
    text: str,
    *,
    start: str | None = None,
    floor: int | None = None,
    accessible_only: bool | None = None,
) -> Answer:
    """Execute a shopper query through the Orchestrator."""
    return finder.run(
        text,
        start=start,
        floor=floor,
        accessible_only=accessible_only,
    )


def answer_question(
    finder: Orchestrator,
    session_id: str,
    item_index: int,
    sku: str,
) -> Answer:
    """Submit a clarification choice to resolve an ambiguous item."""
    return finder.answer_question(
        session_id=session_id,
        item_index=item_index,
        sku=sku,
    )
