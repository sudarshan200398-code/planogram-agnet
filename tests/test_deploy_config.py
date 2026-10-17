"""Deployment files (render.yaml, requirements-api.txt, web/vercel.json) keep the rules in docs/DEPLOY.md."""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RENDER = (ROOT / "render.yaml").read_text(encoding="utf-8")
REQUIREMENTS = (ROOT / "requirements-api.txt").read_text(encoding="utf-8")
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
VERCEL = json.loads((ROOT / "web" / "vercel.json").read_text(encoding="utf-8"))


def _name(requirement: str) -> str:
    return re.split(r"[<>=!~\[ ]", requirement.strip(), maxsplit=1)[0].lower().replace("_", "-")


def _pins() -> dict[str, str]:
    lines = [ln.split("#")[0].strip() for ln in REQUIREMENTS.splitlines()]
    return {_name(ln): ln.split("==", 1)[1] for ln in lines if ln}


def _render_value(key: str) -> str | None:
    match = re.search(rf"^\s*-?\s*{key}:\s*(.+)$", RENDER, re.MULTILINE)
    return match.group(1).strip().strip('"') if match else None


def _env(key: str) -> str | None:
    match = re.search(rf"- key: {key}\n\s+(value|sync): (.+)", RENDER)
    return f"{match.group(1)}={match.group(2).strip().strip(chr(34))}" if match else None


def test_api_requirements_are_exact_pins():
    lines = [ln.split("#")[0].strip() for ln in REQUIREMENTS.splitlines()]
    assert all("==" in ln for ln in lines if ln)


def test_api_requirements_cover_the_engine_and_the_api_extra():
    pins = _pins()
    needed = PYPROJECT["project"]["dependencies"] + [
        r for r in PYPROJECT["project"]["optional-dependencies"]["api"] if _name(r) != "httpx"  # httpx: tests only
    ]
    assert {_name(r) for r in needed} <= set(pins)
    for r in PYPROJECT["project"]["optional-dependencies"]["api"]:
        if "==" in r and _name(r) in pins:
            assert pins[_name(r)] == r.split("==", 1)[1], r


def test_render_runs_one_worker_without_a_model_and_without_secrets():
    start = _render_value("startCommand")
    assert start == "uvicorn api.main:app --host 0.0.0.0 --port $PORT --workers 1 --no-access-log"
    assert _render_value("buildCommand") == "pip install -r requirements-api.txt"
    assert _render_value("healthCheckPath") == "/health"
    assert _render_value("plan") == "free"
    assert _env("PLANOGRAM_PROVIDER") == "value=none"
    assert _env("PLANOGRAM_TRUST_PROXY") == "value=1"
    assert _env("PLANOGRAM_TRUSTED_PROXY_HOPS") == "value=1"  # count X-Forwarded-For from the right
    assert _env("PLANOGRAM_CORS_ORIGINS") == "sync=false"  # set by hand after Vercel gives the URL
    assert _env("PYTHONPATH") == "value=src"
    assert (_env("PYTHON_VERSION") or "").startswith("value=3.12")
    assert not re.search(r"(?i)(api[_-]?key|secret|token|password)", RENDER)


def test_vercel_builds_the_static_app_with_the_security_headers():
    assert VERCEL["buildCommand"] == "npm run build"
    assert VERCEL["outputDirectory"] == "dist"
    headers = {h["key"]: h["value"] for block in VERCEL["headers"] if block["source"] == "/(.*)" for h in block["headers"]}
    assert headers == {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-Frame-Options": "DENY",
        "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
    }


def test_streamlit_requirements_are_separate():
    streamlit = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "streamlit" in streamlit and "uvicorn" not in streamlit
    assert "streamlit" not in REQUIREMENTS
