"""Gemini LLM client using google-genai."""
from __future__ import annotations

import os
import time
from collections.abc import Callable

from ..settings import Settings, load_settings
from .no_model import ModelUnavailableError


def _is_retryable_error(exc: Exception) -> bool:
    """Determine if an error is a 503, 429, timeout, or connection reset."""
    err_str = str(exc).lower()
    if "not found" in err_str:
        return False

    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in (429, 503):
        return True

    if isinstance(exc, (TimeoutError, ConnectionResetError)):
        return True

    return bool(
        "503" in err_str
        or "429" in err_str
        or "unavailable" in err_str
        or "resource_exhausted" in err_str
        or "timeout" in err_str
        or "timed out" in err_str
        or "connection reset" in err_str
    )


class GeminiClient:
    """Client for Google Gemini models using the google-genai SDK.

    Reads GEMINI_API_KEY from environment variables and lazily imports
    google-genai inside the class so test suites do not require the package.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        api_key: str | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        on_call: Callable[[], None] | None = None,
    ) -> None:
        if settings is None:
            settings = load_settings()
        self.settings = settings
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        self.clock = clock
        self.sleep = sleep
        self.on_call = on_call

    def generate(self, system: str, user: str, timeout: float | None = None) -> str:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ImportError(
                "The google-genai package is required to use GeminiClient. "
                "Install it with 'pip install google-genai'."
            ) from exc

        total_budget = timeout if timeout is not None else float(self.settings.model_timeout_seconds)
        start_time = self.clock()
        deadline = start_time + total_budget
        backoffs = [2.0, 5.0]

        for attempt in range(3):
            remaining = deadline - self.clock()
            if remaining < 1.0:
                raise ModelUnavailableError(
                    f"Model deadline exceeded (remaining {remaining:.2f}s < 1.0s)"
                )

            call_timeout_ms = int(remaining * 1000)

            try:
                if self.on_call is not None:
                    self.on_call()

                http_options = types.HttpOptions(timeout=call_timeout_ms) if hasattr(types, "HttpOptions") else None
                client_kwargs = {"api_key": self.api_key}
                if http_options is not None:
                    client_kwargs["http_options"] = http_options
                client = genai.Client(**client_kwargs)

                config_kwargs = {
                    "system_instruction": system,
                    "temperature": 0.0,
                    "max_output_tokens": self.settings.max_tokens,
                    "response_mime_type": "application/json",
                }
                if http_options is not None:
                    config_kwargs["http_options"] = http_options
                config = types.GenerateContentConfig(**config_kwargs)

                response = client.models.generate_content(
                    model=self.settings.model_name,
                    contents=user,
                    config=config,
                )
                return response.text or ""
            except Exception as exc:
                if not _is_retryable_error(exc):
                    raise

                if attempt >= 2:
                    raise ModelUnavailableError(
                        f"Gemini service unavailable after {attempt + 1} attempts: {exc}"
                    ) from exc

                wait_sec = backoffs[attempt]
                remaining_after_wait = (deadline - self.clock()) - wait_sec
                if remaining_after_wait < 1.0:
                    raise ModelUnavailableError(
                        f"Deadline does not allow retry wait of {wait_sec}s: {exc}"
                    ) from exc

                self.sleep(wait_sec)

        raise ModelUnavailableError("Gemini service unavailable")
