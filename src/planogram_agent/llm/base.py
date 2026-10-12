"""LLM client protocol definition."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM model clients."""

    def generate(self, system: str, user: str) -> str:
        """Generate response text given system instructions and user prompt."""
        ...
