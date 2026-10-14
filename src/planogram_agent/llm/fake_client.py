"""Scripted fake LLM client for tests."""
from __future__ import annotations

from collections.abc import Sequence


class FakeLLMClient:
    """Scripted fake LLM client that returns pre-configured responses in order.

    Can also raise scripted exceptions, records every call made to generate,
    and raises a clear error if it runs out of scripted replies.
    """

    def __init__(self, responses: Sequence[str | Exception | type[Exception]] | None = None) -> None:
        self._responses: list[str | Exception | type[Exception]] = (
            list(responses) if responses is not None else []
        )
        self.calls: list[dict[str, object]] = []
        self.timeouts: list[float | None] = []

    def generate(self, system: str, user: str, timeout: float | None = None) -> str:
        self.calls.append({"system": system, "user": user, "timeout": timeout})
        self.timeouts.append(timeout)
        if not self._responses:
            raise RuntimeError("FakeLLMClient ran out of scripted replies")

        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        if isinstance(resp, type) and issubclass(resp, Exception):
            raise resp("Scripted FakeLLMClient exception")

        return str(resp)
