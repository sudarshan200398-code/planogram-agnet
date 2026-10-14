"""Test-first suite for exact full product name matching bug fix."""
from __future__ import annotations

from pathlib import Path

import pytest

from planogram_agent.data_loader import load_dataset
from planogram_agent.matching import decide_match, normalize_text, search_products
from planogram_agent.settings import Settings

STORE_DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(STORE_DEMO_DIR, validate=True)


@pytest.fixture(scope="module")
def settings():
    return Settings()


def test_exact_name_aaa_vs_aa_batteries(dataset, settings):
    """Case (a): exact full name match for AAA batteries must match CHK-BAT-003, not be ambiguous with AA."""
    query = "Store Brand AAA Batteries 8 pack"
    candidates = search_products(query, top_k=settings.top_k, dataset=dataset)
    decision = decide_match(candidates, settings, dataset, query=query)

    assert decision.status == "matched", (
        f"Expected status 'matched', got '{decision.status}' with candidates: "
        f"{[(c.sku, c.name, c.score) for c in decision.candidates]}"
    )
    assert len(decision.candidates) == 1
    assert decision.candidates[0].sku == "CHK-BAT-003"


def test_exact_name_property_over_all_dataset_products(dataset, settings):
    """Case (b): searching any product's full name matches that product, unless a duplicate normalized name exists."""
    failures: list[tuple[str, str, str]] = []

    for p in dataset.products:
        norm_p = normalize_text(p.name)
        # Check if another distinct product shares the exact identical normalized name
        same_name = [
            p2 for p2 in dataset.products
            if p2.sku != p.sku and normalize_text(p2.name) == norm_p
        ]
        if same_name:
            continue

        candidates = search_products(p.name, top_k=settings.top_k, dataset=dataset)
        decision = decide_match(candidates, settings, dataset, query=p.name)

        if decision.status != "matched" or not decision.candidates or decision.candidates[0].sku != p.sku:
            actual_sku = decision.candidates[0].sku if decision.candidates else None
            failures.append((p.sku, p.name, f"status='{decision.status}', top_sku='{actual_sku}'"))

    print(f"\n[Property Test] Failing products count: {len(failures)}")
    for sku, name, reason in failures:
        print(f"  - {sku}: {name} ({reason})")

    assert len(failures) == 0, f"{len(failures)} products failed full-name matching: {failures}"


def test_partial_name_without_size_remains_ambiguous(dataset, settings):
    """Case (c): query without size 'Store Brand AAA Batteries' is NOT matched when near-duplicates exist."""
    query = "Store Brand AAA Batteries"
    candidates = search_products(query, top_k=settings.top_k, dataset=dataset)
    decision = decide_match(candidates, settings, dataset, query=query)

    assert decision.status != "matched", (
        f"Expected query without size to NOT be matched, but got 'matched' with {decision.candidates}"
    )
    assert decision.status == "ambiguous"
    skus = [c.sku for c in decision.candidates]
    assert "CHK-BAT-003" in skus
    assert "CHK-BAT-002" in skus


def test_typo_query_retains_baseline_behavior(dataset, settings):
    """Case (d): typo query 'Store Brand AAAA Batteries 8 pack' behaves exactly as before."""
    query = "Store Brand AAAA Batteries 8 pack"
    candidates = search_products(query, top_k=settings.top_k, dataset=dataset)
    decision = decide_match(candidates, settings, dataset, query=query)

    assert decision.status == "matched"
    assert len(decision.candidates) == 1
    assert decision.candidates[0].sku == "CHK-BAT-003"
    assert pytest.approx(decision.candidates[0].score, abs=0.01) == 0.98


def test_unit_spacing_variation_matches_same_sku(dataset, settings):
    """'Meadow Fresh Whole Milk 1L' (no space) matches the same SKU as 'Meadow Fresh Whole Milk 1 L'."""
    q_nospace = "Meadow Fresh Whole Milk 1L"
    q_space = "Meadow Fresh Whole Milk 1 L"

    c1 = search_products(q_nospace, top_k=settings.top_k, dataset=dataset)
    d1 = decide_match(c1, settings, dataset, query=q_nospace)

    c2 = search_products(q_space, top_k=settings.top_k, dataset=dataset)
    d2 = decide_match(c2, settings, dataset, query=q_space)

    assert d1.status == "matched"
    assert d2.status == "matched"
    assert d1.candidates[0].sku == "DAI-MIL-001"
    assert d2.candidates[0].sku == "DAI-MIL-001"
