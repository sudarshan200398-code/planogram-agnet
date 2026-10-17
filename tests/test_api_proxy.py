"""Rate-limit buckets behind a proxy: the client address is read from X-Forwarded-For counting from the right."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from planogram_agent.settings import load_settings

LIMIT = 2
PROXY = "10.20.0.1"  # an inner proxy hop (used with hops=2)


@pytest.fixture
def limited(monkeypatch):
    def make(trust: bool = True, hops: str | None = None) -> TestClient:
        if trust:
            monkeypatch.setenv("PLANOGRAM_TRUST_PROXY", "1")
        else:
            monkeypatch.delenv("PLANOGRAM_TRUST_PROXY", raising=False)
        if hops is None:
            monkeypatch.delenv("PLANOGRAM_TRUSTED_PROXY_HOPS", raising=False)
        else:
            monkeypatch.setenv("PLANOGRAM_TRUSTED_PROXY_HOPS", hops)
        settings = load_settings().model_copy(update={"api_rate_limit_per_minute": LIMIT})
        return TestClient(create_app(settings=settings))
    return make


def _codes(client: TestClient, headers: list[dict[str, str]]) -> list[int]:
    return [client.get("/stores", headers=h).status_code for h in headers]


def _xff(value: str) -> dict[str, str]:
    return {"X-Forwarded-For": value}


def test_a_forged_first_entry_does_not_change_the_bucket(limited):
    # The client controls everything left of what the proxy appends; the proxy appends the real address.
    with limited() as c:
        forged = [_xff(f"198.51.100.{i}, 203.0.113.7") for i in range(LIMIT + 1)]
        assert _codes(c, forged) == [200] * LIMIT + [429]


def test_two_real_clients_behind_the_proxy_get_separate_buckets(limited):
    with limited() as c:
        same_forgery = "198.51.100.1"
        a = [_xff(f"{same_forgery}, 203.0.113.7")] * (LIMIT + 1)
        b = [_xff(f"{same_forgery}, 203.0.113.8")] * LIMIT
        assert _codes(c, a) == [200] * LIMIT + [429]
        assert _codes(c, b) == [200] * LIMIT


def test_two_trusted_hops(limited):
    # client -> outer proxy (appends the client) -> inner proxy (appends the outer proxy) -> API
    with limited(hops="2") as c:
        forged = [_xff(f"198.51.100.{i}, 203.0.113.7, {PROXY}") for i in range(LIMIT + 1)]
        assert _codes(c, forged) == [200] * LIMIT + [429]
        other = [_xff(f"198.51.100.1, 203.0.113.8, {PROXY}")] * LIMIT
        assert _codes(c, other) == [200] * LIMIT


def test_ipv6_addresses_are_read_too(limited):
    with limited() as c:
        assert _codes(c, [_xff(f"198.51.100.{i}, 2001:db8::7") for i in range(LIMIT + 1)]) == [200] * LIMIT + [429]
        assert _codes(c, [_xff("2001:db8::8")] * LIMIT) == [200] * LIMIT


@pytest.mark.parametrize("values", [
    pytest.param([f"garbage-{i}" for i in range(LIMIT + 1)], id="not-an-ip"),
    pytest.param([f"203.0.113.{i}:4431" for i in range(LIMIT + 1)], id="ip-with-port"),
    pytest.param([f"203.0.113.{i}, " for i in range(LIMIT + 1)], id="empty-last-entry"),
    pytest.param(["", " ", ","], id="blank"),
])
def test_unusable_entries_fall_back_to_the_connection_address(limited, values):
    # Each request carries a different unusable value; all of them count against the one direct address.
    with limited() as c:
        assert _codes(c, [_xff(v) for v in values]) == [200] * LIMIT + [429]


def test_missing_header_falls_back_to_the_connection_address(limited):
    with limited() as c:
        assert _codes(c, [{}] * (LIMIT + 1)) == [200] * LIMIT + [429]


def test_a_header_shorter_than_the_hops_falls_back(limited):
    with limited(hops="2") as c:
        assert _codes(c, [_xff(f"203.0.113.{i}") for i in range(LIMIT + 1)]) == [200] * LIMIT + [429]


@pytest.mark.parametrize("hops", ["0", "-1", "two", ""])
def test_a_bad_hops_setting_means_one_hop(limited, hops):
    with limited(hops=hops) as c:
        assert _codes(c, [_xff(f"198.51.100.{i}, 203.0.113.7") for i in range(LIMIT + 1)]) == [200] * LIMIT + [429]


def test_without_trust_the_header_is_ignored(limited):
    with limited(trust=False, hops="1") as c:
        varied = [_xff(f"198.51.100.{i}, 203.0.113.{i}") for i in range(LIMIT + 1)]
        assert _codes(c, varied) == [200] * LIMIT + [429]
