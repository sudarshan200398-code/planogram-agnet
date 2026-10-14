"""Gemini LLM client using google-genai."""
from __future__ import annotations

import os
import re
import time
from collections.abc import Callable

from ..settings import Settings, load_settings
from .no_model import ModelUnavailableError, QuotaExhaustedError


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
        or "resource has been exhausted" in err_str
        or "quota" in err_str
        or "timeout" in err_str
        or "timed out" in err_str
        or "connection reset" in err_str
    )


def _parse_duration(val: str | float | int | None) -> float | None:
    """Parse duration strings like '6878s', '12.5s', '1h54m38.9s' or numeric values into seconds."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    val = str(val).strip()
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        pass
    pattern = r"^(?:(?P<hours>[\d.]+)h)?(?:(?P<minutes>[\d.]+)m)?(?:(?P<seconds>[\d.]+)s)?$"
    m = re.match(pattern, val)
    if m and any(m.groups()):
        h = float(m.group("hours") or 0)
        m_val = float(m.group("minutes") or 0)
        s = float(m.group("seconds") or 0)
        return h * 3600.0 + m_val * 60.0 + s
    return None


def _parse_quota_error(exc: Exception) -> tuple[bool, float | None, bool]:
    """Inspect an exception for 429 RESOURCE_EXHAUSTED details.

    Returns:
        (is_quota_error, retry_delay_seconds, is_per_day)
    """
    err_str = str(exc)
    err_str_lower = err_str.lower()

    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    status = str(getattr(exc, "status", "") or "").upper()

    is_429 = (
        code == 429
        or status == "RESOURCE_EXHAUSTED"
        or "429" in err_str
        or "resource_exhausted" in err_str_lower
        or "resource has been exhausted" in err_str_lower
        or "quota" in err_str_lower
    )
    if not is_429:
        return False, None, False

    retry_delay: float | None = None
    is_per_day = "perday" in err_str_lower

    details = getattr(exc, "details", None)
    if isinstance(details, (list, tuple)):
        for item in details:
            if isinstance(item, dict):
                if "retryDelay" in item:
                    retry_delay = _parse_duration(item["retryDelay"])
                elif "retry_delay" in item:
                    retry_delay = _parse_duration(item["retry_delay"])

                violations = item.get("violations", [])
                if isinstance(violations, (list, tuple)):
                    for v in violations:
                        if isinstance(v, dict):
                            qid = str(v.get("quotaId") or v.get("quota_id") or "")
                            if "perday" in qid.lower():
                                is_per_day = True

    if retry_delay is None:
        msg = getattr(exc, "message", None) or err_str
        m = re.search(r"retry(?:\s+in|\s+after)?\s+([0-9hms.]+)", str(msg), re.IGNORECASE)
        if m:
            token = m.group(1).rstrip(".,;! ")
            retry_delay = _parse_duration(token)

    return True, retry_delay, is_per_day


class GeminiClient:
    """Client for Google Gemini models using the google-genai SDK.

    Reads GEMINI_API_KEY from environment variables and lazily imports
    google-genai inside the class so test suites do not require the package.
    """

    min_call_timeout: float = 10.0

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
            if remaining < self.min_call_timeout:
                raise ModelUnavailableError(
                    f"Model deadline exceeded (remaining {remaining:.2f}s < {self.min_call_timeout}s)",
                    reason="time_budget",
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

                is_quota, suggested_delay, is_per_day = _parse_quota_error(exc)
                wait_sec = backoffs[attempt] if attempt < len(backoffs) else 0.0

                if is_quota:
                    if is_per_day or (suggested_delay is not None and suggested_delay > wait_sec):
                        raise QuotaExhaustedError(
                            f"Gemini quota exhausted: {exc}",
                            retry_after_seconds=suggested_delay,
                        ) from exc

                if attempt >= 2:
                    if is_quota:
                        raise QuotaExhaustedError(
                            f"Gemini quota exhausted after {attempt + 1} attempts: {exc}",
                            retry_after_seconds=suggested_delay,
                        ) from exc
                    raise ModelUnavailableError(
                        f"Gemini service unavailable after {attempt + 1} attempts: {exc}"
                    ) from exc

                remaining_after_wait = (deadline - self.clock()) - wait_sec
                if remaining_after_wait < self.min_call_timeout:
                    raise ModelUnavailableError(
                        f"Deadline does not allow retry wait of {wait_sec}s: {exc}",
                        reason="time_budget",
                    ) from exc

                self.sleep(wait_sec)

        raise ModelUnavailableError("Gemini service unavailable")
