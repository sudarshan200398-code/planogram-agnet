"""Tests for minimum call timeout and quota exhausted error handling."""
import pytest

from planogram_agent.agents.query import parse_request
from planogram_agent.llm.base import LLMClient
from planogram_agent.llm.gemini_client import GeminiClient
from planogram_agent.llm.no_model import ModelUnavailableError, QuotaExhaustedError
from planogram_agent.settings import Settings, load_settings


class FakeClock:
    def __init__(self, t: float = 0.0):
        self._t = t

    def now(self) -> float:
        return self._t

    def advance(self, s: float) -> None:
        self._t += s


class RaisingFakeClient(LLMClient):
    def __init__(self, exc: Exception, min_call_timeout: float = 1.0):
        self.exc = exc
        self.min_call_timeout = min_call_timeout
        self.call_count = 0

    def generate(self, system: str, user: str, timeout: float | None = None) -> str:
        self.call_count += 1
        raise self.exc


def test_gemini_client_min_call_timeout_attribute():
    assert getattr(GeminiClient, "min_call_timeout", None) == 10.0


def test_gemini_client_never_calls_when_remaining_deadline_below_min_timeout(fake_genai_env):
    ctx = fake_genai_env(["should not be called"])
    clock = FakeClock(0.0)
    client = GeminiClient(
        settings=Settings(model_timeout_seconds=20.0),
        api_key="mock-key",
        clock=clock.now,
    )
    # Remaining timeout = 9.0s < min_call_timeout (10.0s)
    with pytest.raises(ModelUnavailableError) as exc_info:
        client.generate("system", "user", timeout=9.0)

    assert exc_info.value.reason == "time_budget"
    assert ctx.call_count == 0


def test_parse_request_uses_min_call_timeout_from_client():
    client = RaisingFakeClient(ModelUnavailableError("dummy"), min_call_timeout=10.0)
    settings = Settings(model_timeout_seconds=9.0)
    res = parse_request("find milk", client, settings)
    assert client.call_count == 0
    assert res.source == "fallback"
    assert res.fallback_reason == "time_budget"


def test_parse_request_fallback_reason_mappings():
    settings = Settings(model_timeout_seconds=20.0)

    # 1. reason 'time_budget' -> 'time_budget'
    c1 = RaisingFakeClient(ModelUnavailableError("budget spent", reason="time_budget"))
    r1 = parse_request("find milk", c1, settings)
    assert r1.fallback_reason == "time_budget"

    # 2. QuotaExhaustedError -> 'quota_exhausted'
    c2 = RaisingFakeClient(QuotaExhaustedError("daily limit hit", retry_after_seconds=3600.0))
    r2 = parse_request("find milk", c2, settings)
    assert r2.fallback_reason == "quota_exhausted"

    # 3. ModelUnavailableError (no reason) -> 'model_unavailable'
    c3 = RaisingFakeClient(ModelUnavailableError("server down"))
    r3 = parse_request("find milk", c3, settings)
    assert r3.fallback_reason == "model_unavailable"

    # 4. Generic error -> 'model_unavailable'
    c4 = RaisingFakeClient(RuntimeError("network error"))
    r4 = parse_request("find milk", c4, settings)
    assert r4.fallback_reason == "model_unavailable"


def test_settings_default_model_timeout_is_20():
    settings = Settings()
    assert settings.model_timeout_seconds == 20.0

    loaded = load_settings()
    assert loaded.model_timeout_seconds == 20.0


class MockGeminiAPIError(Exception):
    def __init__(self, err_dict: dict):
        super().__init__(err_dict.get("message", "Mock Gemini API Error"))
        self.code = err_dict.get("code")
        self.status = err_dict.get("status")
        self.message = err_dict.get("message")
        self.details = err_dict.get("details", [])
        self.error_dict = err_dict


def test_gemini_client_quota_error_real_gemini_shape(fake_genai_env):
    real_gemini_429 = MockGeminiAPIError({
        "code": 429,
        "status": "RESOURCE_EXHAUSTED",
        "message": "Resource has been exhausted (e.g. check quota). Please retry in 1h54m38.9s.",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                "retryDelay": "6878s",
            },
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [
                    {
                        "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                    }
                ],
            },
        ],
    })
    ctx = fake_genai_env([real_gemini_429])
    clock = FakeClock(0.0)
    client = GeminiClient(
        settings=Settings(model_timeout_seconds=20.0),
        api_key="mock-key",
        clock=clock.now,
        sleep=clock.advance,
    )

    with pytest.raises(QuotaExhaustedError) as exc_info:
        client.generate("system", "user")

    assert exc_info.value.retry_after_seconds == 6878.0
    assert ctx.call_count == 1
    assert clock.now() == 0.0  # Did not sleep, raised after 1 call


def test_gemini_client_quota_error_message_text_only(fake_genai_env):
    msg_only_err = RuntimeError("Resource has been exhausted. Please retry in 1h54m38.9s.")
    ctx = fake_genai_env([msg_only_err])
    clock = FakeClock(0.0)
    client = GeminiClient(
        settings=Settings(model_timeout_seconds=20.0),
        api_key="mock-key",
        clock=clock.now,
        sleep=clock.advance,
    )

    with pytest.raises(QuotaExhaustedError) as exc_info:
        client.generate("system", "user")

    assert exc_info.value.retry_after_seconds == pytest.approx(6878.9, abs=0.1)
    assert ctx.call_count == 1
    assert clock.now() == 0.0


def test_gemini_client_429_short_delay_is_retried(fake_genai_env):
    short_delay_err = MockGeminiAPIError({
        "code": 429,
        "status": "RESOURCE_EXHAUSTED",
        "message": "Rate limit exceeded. Please retry in 1s.",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                "retryDelay": "1s",
            }
        ],
    })
    valid_json = '{"intent": "find", "items": [{"text": "milk", "qty": 1}]}'
    ctx = fake_genai_env([short_delay_err, valid_json])
    clock = FakeClock(0.0)
    client = GeminiClient(
        settings=Settings(model_timeout_seconds=20.0),
        api_key="mock-key",
        clock=clock.now,
        sleep=clock.advance,
    )

    res = client.generate("system", "user")
    assert "milk" in res
    assert ctx.call_count == 2
    assert clock.now() == 2.0  # Retried with the normal 2s wait


def test_gemini_client_perday_quota_not_retried_even_with_short_delay(fake_genai_env):
    perday_err = MockGeminiAPIError({
        "code": 429,
        "status": "RESOURCE_EXHAUSTED",
        "message": "Rate limit exceeded. Please retry in 1s.",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                "retryDelay": "1s",
            },
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [
                    {
                        "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                    }
                ],
            },
        ],
    })
    ctx = fake_genai_env([perday_err])
    clock = FakeClock(0.0)
    client = GeminiClient(
        settings=Settings(model_timeout_seconds=20.0),
        api_key="mock-key",
        clock=clock.now,
        sleep=clock.advance,
    )

    with pytest.raises(QuotaExhaustedError) as exc_info:
        client.generate("system", "user")

    assert ctx.call_count == 1
    assert clock.now() == 0.0
