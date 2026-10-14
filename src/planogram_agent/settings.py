"""Configuration thresholds and limits for the planogram agent."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Settings(BaseModel):
    accept_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    ask_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    margin: float = Field(default=0.1, ge=0.0)
    top_k: int = Field(default=5, ge=1)
    max_items: int = Field(default=20, ge=1)
    max_query_chars: int = Field(default=500, ge=1)
    max_agent_steps: int = Field(default=20, ge=1)
    max_seconds: int = Field(default=30, ge=1)
    exact_stop_limit: int = Field(default=8, ge=1)
    max_plan_evaluations: int = Field(default=200000, ge=1)
    retries: int = Field(default=1, ge=0)
    provider: str = Field(default="gemini")
    model_name: str = Field(default="gemini-3-flash-preview")
    max_tokens: int = Field(default=1000, ge=1)
    session_ttl_seconds: int = Field(default=600, ge=1)
    max_repairs: int = Field(default=1, ge=0)


def _find_default_settings_file() -> Path | None:
    cwd_path = Path("config/settings.json")
    if cwd_path.is_file():
        return cwd_path
    repo_path = Path(__file__).resolve().parent.parent.parent / "config" / "settings.json"
    if repo_path.is_file():
        return repo_path
    return None


def load_settings(path: Path | str | None = None, **overrides: Any) -> Settings:
    """Load settings from a JSON file (defaults to config/settings.json) or fall back to defaults.

    Overrides can be provided as keyword arguments.
    """
    if path is not None:
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        data.update(overrides)
        return Settings.model_validate(data)

    default_file = _find_default_settings_file()
    if default_file is not None:
        data = json.loads(default_file.read_text(encoding="utf-8"))
        data.update(overrides)
        return Settings.model_validate(data)

    return Settings(**overrides)
