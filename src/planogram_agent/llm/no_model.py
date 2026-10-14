"""No-model client implementation raising ModelUnavailableError."""
from __future__ import annotations

from .base import LLMClient


class ModelUnavailableError(Exception):
    """Raised when an AI model is unavailable or no model is configured."""

    def __init__(self, message: str = "No AI model configured or available", reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason


class QuotaExhaustedError(ModelUnavailableError):
    """Raised when an AI model's quota has been exhausted."""

    def __init__(
        self,
        message: str = "AI model quota exhausted",
        retry_after_seconds: float | None = None,
        reason: str = "quota_exhausted",
    ) -> None:
        super().__init__(message, reason=reason)
        self.retry_after_seconds = retry_after_seconds


class NoModelClient(LLMClient):
    """Deterministic client representing an unavailable or unconfigured AI model.

    Always raises ModelUnavailableError on generate(), prompting caller retries
    and deterministic fallback.
    """

    def generate(self, system: str, user: str, timeout: float | None = None) -> str:
        raise ModelUnavailableError("No AI model configured or available")
