"""API settings read from the environment. Limits and thresholds live in config/settings.json."""
from __future__ import annotations

import os

CORS_ORIGINS_ENV = "PLANOGRAM_CORS_ORIGINS"  # comma-separated origins; empty or unset = no cross-origin access
TRUST_PROXY_ENV = "PLANOGRAM_TRUST_PROXY"  # "1" = take the client address from X-Forwarded-For


def cors_origins() -> list[str]:
    raw = os.environ.get(CORS_ORIGINS_ENV, "")
    return [o.strip() for o in raw.split(",") if o.strip()]


def trust_proxy() -> bool:
    return os.environ.get(TRUST_PROXY_ENV, "").strip().lower() in {"1", "true", "yes"}
