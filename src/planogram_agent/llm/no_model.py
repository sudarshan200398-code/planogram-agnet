"""No-model client implementation raising ModelUnavailableError."""
from __future__ import annotations

from .base import LLMClient


class ModelUnavailableError(Exception):
    """Raised when an AI model is unavailable or no model is configured."""


class NoModelClient(LLMClient):
    """Deterministic client representing an unavailable or unconfigured AI model.

    Always raises ModelUnavailableError on generate(), prompting caller retries
    and deterministic fallback.
    """

    def generate(self, system: str, user: str, timeout: float | None = None) -> str:
        raise ModelUnavailableError("No AI model configured or available")
