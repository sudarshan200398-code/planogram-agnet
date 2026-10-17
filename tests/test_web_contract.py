"""The web app's contract files (web/openapi.json, web/src/api/fixtures/*.json) match the current API."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _exporter():
    spec = importlib.util.spec_from_file_location("export_web_contract", ROOT / "scripts" / "export_web_contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_web_contract_files_are_current_and_deterministic(monkeypatch):
    monkeypatch.setenv("PLANOGRAM_PROVIDER", "none")
    exporter = _exporter()
    first = exporter.build_contract()
    assert first == exporter.build_contract(), "the export is not deterministic"
    committed = {
        f"src/api/fixtures/{p.name}": p.read_text(encoding="utf-8").replace("\r\n", "\n")
        for p in (ROOT / "web" / "src" / "api" / "fixtures").glob("*.json")
    }
    committed["openapi.json"] = (ROOT / "web" / "openapi.json").read_text(encoding="utf-8").replace("\r\n", "\n")
    stale = sorted(k for k in first.keys() | committed.keys() if first.get(k) != committed.get(k))
    assert stale == [], (
        "web contract files are stale; regenerate with: "
        "$env:PLANOGRAM_PROVIDER='none'; python scripts/export_web_contract.py; npm --prefix web run gen:api "
        f"-> {stale}"
    )
