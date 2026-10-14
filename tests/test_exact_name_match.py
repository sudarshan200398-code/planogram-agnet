"""Test-first suite for exact full product name matching bug fix."""
from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest
from rapidfuzz import fuzz, process

from planogram_agent.data_loader import load_dataset
from planogram_agent.matching import (
    decide_match,
    get_search_index,
    normalize_text,
    search_products,
)
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


def test_exact_name_mutation_without_exact_rule(dataset, settings):
    """Mutation check: emptying exact-name dictionary causes decide_match on AAA batteries to NOT match."""
    query = "Store Brand AAA Batteries 8 pack"
    candidates = search_products(query, top_k=settings.top_k, dataset=dataset)
    index = get_search_index(dataset)

    saved_dict = index.norm_name_to_skus
    try:
        index.norm_name_to_skus = {}
        decision = decide_match(candidates, settings, dataset, query=query)
        assert decision.status != "matched", (
            f"Expected decide_match on '{query}' to NOT be matched when exact-name index is empty, "
            f"got status='{decision.status}'"
        )
    finally:
        index.norm_name_to_skus = saved_dict


def compute_fast_prefilter_products(dataset):
    """Pairwise similarity prefilter using union of ratio and token_set_ratio matrices >= 90."""
    norm_names = [normalize_text(p.name) for p in dataset.products]
    m_ratio = process.cdist(norm_names, norm_names, scorer=fuzz.ratio, workers=-1)
    m_tokenset = process.cdist(norm_names, norm_names, scorer=fuzz.token_set_ratio, workers=-1)
    np.fill_diagonal(m_ratio, 0)
    np.fill_diagonal(m_tokenset, 0)
    mask = (m_ratio >= 90) | (m_tokenset >= 90)
    candidate_indices = np.where(mask.any(axis=1))[0]
    return [dataset.products[i] for i in candidate_indices]


def test_exact_name_property_over_all_dataset_products(dataset, settings):
    """Case (b): searching any product's full name matches that product (fast version).

    Uses rapidfuzz.process.cdist over normalized names (fuzz.ratio >= 90 or fuzz.token_set_ratio >= 90)
    to prefilter near-duplicate candidates, and computes the sensitive set within that subset.
    Asserts:
    (a) set is not empty and contains CHK-BAT-002 and CHK-BAT-003
    (b) for every product in the set whose normalised name is unique, decide_match returns matched with that SKU
    Also tests a fixed-seed random sample of 150 products. Target: under 8 seconds.
    """
    norm_name_to_skus = defaultdict(list)
    for p in dataset.products:
        norm_name_to_skus[normalize_text(p.name)].append(p.sku)

    candidate_products = compute_fast_prefilter_products(dataset)
    print(f"\n[Fast Prefilter] Selected {len(candidate_products)} products out of {len(dataset.products)}")

    # Compute sensitive set dynamically inside prefiltered candidates
    sensitive_products = []
    for p in candidate_products:
        candidates = search_products(p.name, top_k=settings.top_k, dataset=dataset)
        if not candidates or candidates[0].sku != p.sku:
            sensitive_products.append(p)
        elif len(candidates) >= 2 and (candidates[0].score - candidates[1].score <= settings.margin + 1e-9):
            sensitive_products.append(p)

    sensitive_skus = {p.sku for p in sensitive_products}

    # Print size, SKUs, and names
    print(f"\n[Fast Sensitive Set] Computed {len(sensitive_products)} sensitive products from data:")
    for p in sensitive_products:
        print(f"  - {p.sku}: {p.name}")

    # (a) Assert set is not empty and contains CHK-BAT-002 and CHK-BAT-003
    assert len(sensitive_products) > 0, "Sensitive set must not be empty"
    assert "CHK-BAT-002" in sensitive_skus, "Sensitive set must contain CHK-BAT-002"
    assert "CHK-BAT-003" in sensitive_skus, "Sensitive set must contain CHK-BAT-003"

    # (b) Assert for every product in the set whose normalized name is unique, decide_match returns matched
    for p in sensitive_products:
        norm_p = normalize_text(p.name)
        if len(norm_name_to_skus[norm_p]) > 1:
            continue
        cands = search_products(p.name, top_k=settings.top_k, dataset=dataset)
        decision = decide_match(cands, settings, dataset, query=p.name)
        assert decision.status == "matched", (
            f"Expected matched for sensitive SKU {p.sku} ('{p.name}'), got {decision.status}"
        )
        assert decision.candidates[0].sku == p.sku

    # Also test fixed-seed random sample of 150 products
    rng = random.Random(42)
    sample_150 = rng.sample(dataset.products, 150)
    for p in sample_150:
        norm_p = normalize_text(p.name)
        if len(norm_name_to_skus[norm_p]) > 1:
            continue
        cands = search_products(p.name, top_k=settings.top_k, dataset=dataset)
        decision = decide_match(cands, settings, dataset, query=p.name)
        assert decision.status == "matched", (
            f"Expected matched for sampled SKU {p.sku} ('{p.name}'), got {decision.status}"
        )
        assert decision.candidates[0].sku == p.sku


@pytest.mark.slow
def test_exact_name_property_slow_full_scan(dataset, settings):
    """Full 971-product scan and recall check against fast prefilter."""
    norm_name_to_skus = defaultdict(list)
    for p in dataset.products:
        norm_name_to_skus[normalize_text(p.name)].append(p.sku)

    # Compute full sensitive set over all 971 products
    full_sensitive_products = []
    for p in dataset.products:
        candidates = search_products(p.name, top_k=settings.top_k, dataset=dataset)
        if not candidates or candidates[0].sku != p.sku:
            full_sensitive_products.append(p)
        elif len(candidates) >= 2 and (candidates[0].score - candidates[1].score <= settings.margin + 1e-9):
            full_sensitive_products.append(p)

    full_sensitive_skus = {p.sku for p in full_sensitive_products}

    print(f"\n[Slow Sensitive Set] Computed {len(full_sensitive_products)} sensitive products from all {len(dataset.products)} products:")
    for p in full_sensitive_products:
        print(f"  - {p.sku}: {p.name}")

    # Recall check: fast prefilter must contain every product of the full sensitive set
    prefilter_products = compute_fast_prefilter_products(dataset)
    prefilter_skus = {p.sku for p in prefilter_products}

    missing_skus = full_sensitive_skus - prefilter_skus
    if missing_skus:
        missing_products = [p for p in full_sensitive_products if p.sku in missing_skus]
        missing_details = [f"{p.sku}: {p.name}" for p in missing_products]
        pytest.fail(
            f"Recall check failed: fast prefilter missed {len(missing_skus)} sensitive product(s):\n"
            + "\n".join(f"  - {d}" for d in missing_details)
        )
    assert full_sensitive_skus.issubset(prefilter_skus), "Fast prefilter must contain every sensitive product"

    # Full sensitive set matching check
    for p in full_sensitive_products:
        norm_p = normalize_text(p.name)
        if len(norm_name_to_skus[norm_p]) > 1:
            continue
        cands = search_products(p.name, top_k=settings.top_k, dataset=dataset)
        decision = decide_match(cands, settings, dataset, query=p.name)
        assert decision.status == "matched", (
            f"Expected matched for sensitive SKU {p.sku} ('{p.name}'), got {decision.status}"
        )
        assert decision.candidates[0].sku == p.sku


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
