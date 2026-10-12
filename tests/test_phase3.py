"""Tests for Phase 3 setup: demo store validation, broken data rejection, settings, and golden queries."""
import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from planogram_agent.data_loader import load_dataset, load_golden_queries
from planogram_agent.settings import Settings, load_settings
from planogram_agent.validators import (
    DataValidationError,
    validate_graph_data,
    validate_inventory,
    validate_planogram,
    validate_products,
)

STORE_DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"
GOLDEN_QUERIES_PATH = Path(__file__).resolve().parent / "golden_queries.json"


def test_load_store_demo_passes_validation():
    """data/store_demo must load and pass all validators."""
    ds = load_dataset(STORE_DEMO_DIR, validate=True)
    assert ds.graph.store_id == "demo_supermarket"
    assert ds.graph.floors == [1, 2]
    assert len(ds.graph.nodes) == 53
    assert len(ds.graph.edges) == 74
    assert len(ds.graph.connectors) == 3
    assert len(ds.products) == 971
    assert len(ds.planogram) == 974
    assert len(ds.inventory) == 971

    # Individual validators should return zero issues
    assert validate_graph_data(ds.graph) == []
    assert validate_products(ds.products) == []
    assert validate_planogram(ds.planogram, ds.products, ds.graph) == []
    assert validate_inventory(ds.inventory, ds.products) == []


def test_reject_broken_store_demo_missing_map_point(tmp_path):
    """A copy of data/store_demo with a shelf row pointing to a missing map point must be rejected."""
    for item in STORE_DEMO_DIR.iterdir():
        if item.is_file():
            shutil.copy(item, tmp_path / item.name)

    # Break planogram.csv by pointing a shelf row to an unknown map node
    planogram_file = tmp_path / "planogram.csv"
    lines = planogram_file.read_text(encoding="utf-8").splitlines()
    # Change node_id in line 1 (the first data row) to MISSING_MAP_POINT
    cols = lines[1].split(",")
    cols[-1] = "MISSING_MAP_POINT"
    lines[1] = ",".join(cols)
    planogram_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(DataValidationError) as exc_info:
        load_dataset(tmp_path, validate=True)

    issues = exc_info.value.issues
    assert any("unknown node MISSING_MAP_POINT" in issue for issue in issues)


def test_load_settings_file():
    """Settings file must load defaults and validate constraints."""
    s = load_settings()
    assert s.accept_threshold == 0.85
    assert s.ask_threshold == 0.5
    assert s.margin == 0.1
    assert s.top_k == 5
    assert s.max_items == 20
    assert s.max_query_chars == 500
    assert s.max_agent_steps == 20
    assert s.max_seconds == 30
    assert s.exact_stop_limit == 8
    assert s.retries == 1

    # Overrides should apply cleanly
    s_overridden = load_settings(top_k=10, retries=2)
    assert s_overridden.top_k == 10
    assert s_overridden.retries == 2
    assert s_overridden.accept_threshold == 0.85

    # Boundary checks via Pydantic
    with pytest.raises(ValidationError):
        Settings(accept_threshold=1.5)
    with pytest.raises(ValidationError):
        Settings(top_k=0)


def test_load_settings_from_custom_file_and_fallback(tmp_path, monkeypatch):
    """Custom settings file can be loaded, and fallback works if config file is missing."""
    custom_file = tmp_path / "custom_settings.json"
    custom_file.write_text(json.dumps({
        "accept_threshold": 0.9,
        "ask_threshold": 0.6,
        "margin": 0.05,
        "top_k": 3,
        "max_items": 10,
        "max_query_chars": 200,
        "max_agent_steps": 15,
        "max_seconds": 25,
        "exact_stop_limit": 5,
        "retries": 3,
    }), encoding="utf-8")

    loaded = load_settings(custom_file)
    assert loaded.accept_threshold == 0.9
    assert loaded.top_k == 3
    assert loaded.retries == 3

    # Fallback to built-in defaults when default config file does not exist
    monkeypatch.setattr("planogram_agent.settings._find_default_settings_file", lambda: None)
    fallback = load_settings()
    assert fallback.accept_threshold == 0.85
    assert fallback.top_k == 5


def test_load_golden_queries():
    """golden_queries.json must load cleanly with expected structure and case count."""
    data = load_golden_queries()
    assert isinstance(data, dict)
    assert "cases" in data
    assert "default_start" in data
    assert data["default_start"] == "L1_ENTRANCE"
    assert len(data["cases"]) == 85

    # Check explicit path loading
    data_explicit = load_golden_queries(GOLDEN_QUERIES_PATH)
    assert len(data_explicit["cases"]) == 85

    first_case = data["cases"][0]
    assert first_case["id"] == "EXA-01"
    assert "query" in first_case
    assert "expect" in first_case
