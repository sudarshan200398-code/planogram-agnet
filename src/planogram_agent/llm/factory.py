"""Factory to create LLM clients based on configuration."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import LLMClient
from ..settings import Settings, load_settings


def make_client(settings: Settings | None = None) -> LLMClient:
    """Instantiate an LLMClient based on the settings provider."""
    if settings is None:
        settings = load_settings()

    provider = settings.provider.lower().strip()
    if provider == "gemini":
        from .gemini_client import GeminiClient

        return GeminiClient(settings=settings)
    elif provider == "fake":
        from .fake_client import FakeLLMClient

        return FakeLLMClient()
    elif provider == "none":
        from .no_model import NoModelClient

        return NoModelClient()
    else:
        raise ValueError(
            f"Unknown LLM provider '{settings.provider}'. Supported providers are: 'gemini', 'fake', 'none'."
        )
