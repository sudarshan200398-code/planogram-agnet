"""API settings read from the environment. Limits and thresholds live in config/settings.json."""
from __future__ import annotations

import os

CORS_ORIGINS_ENV = "PLANOGRAM_CORS_ORIGINS"  # comma-separated origins; empty or unset = no cross-origin access
TRUST_PROXY_ENV = "PLANOGRAM_TRUST_PROXY"  # "1" = take the client address from X-Forwarded-For
TRUSTED_PROXY_HOPS_ENV = "PLANOGRAM_TRUSTED_PROXY_HOPS"  # trusted proxies in front of the API (default 1)


def cors_origins() -> list[str]:
    raw = os.environ.get(CORS_ORIGINS_ENV, "")
    return [o.strip() for o in raw.split(",") if o.strip()]


def trust_proxy() -> bool:
    return os.environ.get(TRUST_PROXY_ENV, "").strip().lower() in {"1", "true", "yes"}


def trusted_proxy_hops() -> int:
    """How many X-Forwarded-For entries, counted from the right, were added by proxies we trust (at least 1)."""
    raw = os.environ.get(TRUSTED_PROXY_HOPS_ENV, "").strip()
    return int(raw) if raw.isdigit() and int(raw) >= 1 else 1
