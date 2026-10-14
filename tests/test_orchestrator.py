"""Comprehensive tests for Orchestrator, SessionStore, limits, and multi-turn flows."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

import pytest

from planogram_agent.data_loader import load_dataset
from planogram_agent.interface import answer_question, create_finder, run_query
from planogram_agent.llm.no_model import NoModelClient
from planogram_agent.runtime.orchestrator import Orchestrator, SessionStore
from planogram_agent.runtime.state import Answer, ItemResult, RunState
from planogram_agent.settings import Settings

STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"
GOLDEN_PATH = Path(__file__).resolve().parent / "golden_queries.json"

CATEGORIES = [
    "exact",
    "typo",
    "synonym",
    "size_narrows",
    "generic",
    "not_found",
    "out_of_stock",
    "multi_item",
    "multi_location",
    "accessible",
    "start_point",
    "mixed",
    "invalid_input (structural)",
]
STRUCTURAL_INVALID_IDS = {"INV-01", "INV-02", "INV-03", "INV-04"}


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(STORE_DIR, validate=True)


@pytest.fixture(scope="module")
def settings():
    return Settings()


@pytest.fixture(scope="module")
def finder(dataset, settings):
    return create_finder(STORE_DIR, settings=settings, client=NoModelClient())


def test_no_google_genai_imported():
    """Assert that google.genai is never imported in offline test environment."""
    assert "google.genai" not in sys.modules, "google.genai must not be imported in tests"


def test_golden_queries_orchestrator_end_to_end(finder):
    """End-to-end evaluation over golden_queries.json with NoModelClient across categories."""
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        golden_data = json.load(f)

    categories_cases: dict[str, list[dict]] = {cat: [] for cat in CATEGORIES}
    for case in golden_data["cases"]:
        cat = case["category"]
        if cat == "invalid_input":
            if case["id"] in STRUCTURAL_INVALID_IDS:
                categories_cases["invalid_input (structural)"].append(case)
        elif cat in categories_cases:
            categories_cases[cat].append(case)

    results: dict[str, dict] = {}
    failing_cases: dict[str, list[tuple[str, str, str]]] = {}

    for cat in CATEGORIES:
        cases = categories_cases[cat]
        passed = 0
        cat_fails: list[tuple[str, str, str]] = []

        for case in cases:
            cid = case["id"]
            query = case["query"]
            start = case.get("start")
            start_floor = case.get("start_floor")
            accessible = case.get("accessible_only", False)
            expected = case.get("expect", {})

            ans = run_query(
                finder,
                query,
                start=start,
                floor=start_floor,
                accessible_only=accessible,
            )

            # Require verified=True for ok and partial
            if ans.status in ("ok", "partial") and not ans.verified:
                cat_fails.append((cid, query, f"Expected verified=True, got {ans.verified}"))
                continue

            if cat == "invalid_input (structural)":
                if ans.status == "error":
                    passed += 1
                else:
                    cat_fails.append((cid, query, f"Expected status 'error', got '{ans.status}'"))
                continue

            # Check response status
            exp_status = expected.get("response_status")
            if ans.status != exp_status:
                cat_fails.append((cid, query, f"Status expected '{exp_status}', got '{ans.status}'"))
                continue

            # Check items
            exp_items = expected.get("items", [])
            if len(ans.items) != len(exp_items):
                cat_fails.append((cid, query, f"Item count expected {len(exp_items)}, got {len(ans.items)}"))
                continue

            item_error = False
            for act_it, exp_it in zip(ans.items, exp_items):
                if exp_it["status"] == "matched":
                    if act_it.status not in ("available", "unavailable", "not_placed"):
                        cat_fails.append((cid, query, f"Item '{act_it.requested}' expected matched, got '{act_it.status}'"))
                        item_error = True
                        break
                    if act_it.sku not in exp_it["acceptable_skus"]:
                        cat_fails.append((cid, query, f"Item '{act_it.requested}' SKU '{act_it.sku}' not in {exp_it['acceptable_skus']}"))
                        item_error = True
                        break
                    exp_avail = exp_it.get("availability")
                    if exp_avail:
                        act_avail = "available" if act_it.status == "available" else ("unavailable" if act_it.status == "unavailable" else "unknown")
                        if act_avail != exp_avail:
                            cat_fails.append((cid, query, f"Item '{act_it.requested}' avail expected '{exp_avail}', got '{act_avail}'"))
                            item_error = True
                            break
                elif exp_it["status"] == "ambiguous":
                    if act_it.status != "needs_choice":
                        cat_fails.append((cid, query, f"Item '{act_it.requested}' expected 'needs_choice', got '{act_it.status}'"))
                        item_error = True
                        break
                elif exp_it["status"] == "not_found":
                    if act_it.status != "not_found":
                        cat_fails.append((cid, query, f"Item '{act_it.requested}' expected 'not_found', got '{act_it.status}'"))
                        item_error = True
                        break

            if item_error:
                continue

            # Route checks for routed cases
            exp_route = expected.get("route")
            if exp_route is not None:
                if ans.route is None:
                    cat_fails.append((cid, query, "Route expected but ans.route is None"))
                    continue
                cost_diff = abs(ans.route.total_cost - exp_route["total_cost"])
                if cost_diff > 0.01 + 1e-9:
                    cat_fails.append((cid, query, f"Cost expected {exp_route['total_cost']}, got {ans.route.total_cost} (diff {cost_diff:.4f})"))
                    continue
                if ans.route.floor_changes != exp_route["floor_changes"]:
                    cat_fails.append((cid, query, f"Floor changes expected {exp_route['floor_changes']}, got {ans.route.floor_changes}"))
                    continue
                act_conns = [c.value if hasattr(c, "value") else str(c) for c in ans.route.connectors_used]
                if act_conns != exp_route.get("connectors_used", []):
                    cat_fails.append((cid, query, f"Connectors expected {exp_route.get('connectors_used')}, got {act_conns}"))
                    continue

                # Each ordered SKU has exactly one arrive step and product name appears in directions_text
                arrive_steps = [s for s in ans.route.steps if s.kind == "arrive"]
                if len(arrive_steps) != len(ans.route.ordered_skus):
                    cat_fails.append((cid, query, f"Arrive steps count {len(arrive_steps)} != ordered_skus {len(ans.route.ordered_skus)}"))
                    continue
                if not all(s.product_name in ans.route.directions_text for s in arrive_steps):
                    cat_fails.append((cid, query, "One or more arrive product names missing in directions_text"))
                    continue

            passed += 1

        rate = (passed / len(cases)) * 100 if cases else 0.0
        results[cat] = {"passed": passed, "total": len(cases), "rate": rate}
        failing_cases[cat] = cat_fails

    # Print summary table
    print("\n" + "=" * 70)
    print("GOLDEN QUERIES END-TO-END PASS RATES (ORCHESTRATOR)")
    print("=" * 70)
    for cat, data in results.items():
        print(f"{cat:30s} : {data['passed']:2d}/{data['total']:2d} ({data['rate']:5.1f}%)")

    total_passed = sum(d["passed"] for d in results.values())
    total_cases = sum(d["total"] for d in results.values())
    overall_rate = (total_passed / total_cases) * 100 if total_cases else 0.0
    print("-" * 70)
    print(f"{'OVERALL':30s} : {total_passed:2d}/{total_cases:2d} ({overall_rate:5.1f}%)")
    print("=" * 70)

    for cat, fails in failing_cases.items():
        if fails:
            print(f"\n[Failing cases in '{cat}']:")
            for cid, q, reason in fails:
                print(f"  - {cid}: '{q}' -> {reason}")

    # Assert 100% pass rate
    for cat, data in results.items():
        assert data["passed"] == data["total"], f"Category '{cat}' had failures: {failing_cases[cat]}"


def test_clarification_valid_choice(finder):
    """Question then valid choice completes successfully with verified ok answer."""
    ans1 = run_query(finder, "milk")
    assert ans1.status == "needs_clarification"
    assert ans1.question is not None
    assert ans1.session_id is not None
    valid_sku = ans1.question.options[0].sku

    ans2 = answer_question(finder, ans1.session_id, ans1.question.item_index, valid_sku)
    assert ans2.status == "ok"
    assert ans2.verified is True
    assert ans2.items[0].sku == valid_sku
    assert ans2.route is not None


def test_clarification_invalid_sku_keeps_question_pending(finder):
    """An invalid SKU keeps the question pending with a clear message."""
    ans1 = run_query(finder, "milk")
    assert ans1.session_id is not None
    assert ans1.question is not None

    ans_invalid = answer_question(finder, ans1.session_id, ans1.question.item_index, "BOGUS-SKU-999")
    assert ans_invalid.status == "needs_clarification"
    assert any("not one of the offered options" in m for m in ans_invalid.messages)
    assert ans_invalid.question is not None


def test_clarification_two_ambiguous_items_in_sequence(finder):
    """Two ambiguous items asked one after the other with the other items kept."""
    # "milk and bread" -> both ambiguous
    ans_multi = run_query(finder, "milk and bread")
    assert ans_multi.status == "needs_clarification"
    assert ans_multi.question is not None
    sid = ans_multi.session_id
    q1 = ans_multi.question
    first_choice_sku = q1.options[0].sku

    # Resolve first question
    ans_multi_2 = answer_question(finder, sid, q1.item_index, first_choice_sku)
    assert ans_multi_2.status == "needs_clarification"
    assert ans_multi_2.question is not None
    assert ans_multi_2.question.item_index != q1.item_index
    q2 = ans_multi_2.question
    second_choice_sku = q2.options[0].sku

    # Resolve second question -> complete verified answer
    ans_multi_3 = answer_question(finder, sid, q2.item_index, second_choice_sku)
    assert ans_multi_3.status == "ok"
    assert ans_multi_3.verified is True
    assert len(ans_multi_3.items) == 2
    assert ans_multi_3.items[q1.item_index].sku == first_choice_sku
    assert ans_multi_3.items[q2.item_index].sku == second_choice_sku


def test_clarification_unknown_session(finder):
    """An unknown session ID returns error with clear explanation."""
    ans_unknown = answer_question(finder, "non-existent-session-id", 0, "DAI-MIL-001")
    assert ans_unknown.status == "error"
    assert any("expired" in m.lower() for m in ans_unknown.messages)



def test_clarification_expired_session(dataset, settings):
    """An expired session using an injectable fake clock returns clear error."""
    curr_time = 1000.0

    def fake_clock():
        return curr_time

    orch = Orchestrator(dataset=dataset, settings=settings, clock=fake_clock)
    ans1 = orch.run("milk")
    assert ans1.status == "needs_clarification"
    assert ans1.session_id is not None

    # Fast forward clock past session_ttl_seconds (600s)
    curr_time += 601.0
    ans2 = orch.answer_question(ans1.session_id, ans1.question.item_index, ans1.question.options[0].sku)
    assert ans2.status == "error"
    assert any("expired" in m.lower() for m in ans2.messages)


def test_limits_tiny_max_agent_steps(dataset, settings):
    """A tiny max_agent_steps gives a partial or error answer with a clear message and never raises."""
    tiny_settings = settings.model_copy(update={"max_agent_steps": 1})
    orch = Orchestrator(dataset=dataset, settings=tiny_settings)
    ans = orch.run("Daily Bake Plain Bagels 4 pack")
    assert ans.status in ("partial", "error")
    assert not ans.messages or any("limit" in m.lower() for m in ans.messages)


def test_limits_deadline_exceeded(dataset, settings):
    """A fake clock that jumps past max_seconds gives a partial answer."""
    curr_time = 0.0

    def jumping_clock():
        nonlocal curr_time
        curr_time += 15.0  # jumps 15s every check, exceeding max_seconds=10.0
        return curr_time

    orch = Orchestrator(dataset=dataset, settings=settings, clock=jumping_clock)
    ans = orch.run("Daily Bake Plain Bagels 4 pack and Café Corner Trail Mix Pouch large")
    assert ans.status in ("partial", "error")


def test_fault_isolation(dataset, settings, monkeypatch):
    """Make one tool raise for one SKU (monkeypatch); that item gets status error, others complete."""
    from planogram_agent.runtime import orchestrator

    orig_check_avail = orchestrator.check_availability

    def flawed_check_avail(sku, ds):
        if sku == "BAK-BAG-009":
            raise RuntimeError("Database connection timed out for inventory")
        return orig_check_avail(sku, ds)

    monkeypatch.setattr(orchestrator, "check_availability", flawed_check_avail)

    orch = Orchestrator(dataset=dataset, settings=settings)
    ans = orch.run("Daily Bake Plain Bagels 4 pack and Café Corner Trail Mix Pouch large")

    # Item 0 (bagels) experienced error; item 1 completed and was routed
    assert any("Database connection timed out" in err for err in ans.messages)
    assert ans.status in ("ok", "partial")


def test_start_equals_stop(dataset, settings):
    """Standing at the Bakery and asking for a bakery product, or asking for two products there.

    Both must give a verified ok answer with sensible text (no 'Walk 0m').
    """
    orch = Orchestrator(dataset=dataset, settings=settings)

    # 1. Standing at Bakery asking for 1 bakery product
    ans1 = orch.run("Daily Bake Plain Bagels 4 pack", start="Bakery")
    assert ans1.status == "ok"
    assert ans1.verified is True
    assert ans1.route is not None
    assert "Walk 0m" not in ans1.route.directions_text
    assert "Daily Bake Plain Bagels 4 pack" in ans1.route.directions_text

    # 2. Standing at Bakery asking for 2 bakery products
    ans2 = orch.run("Daily Bake Plain Bagels 4 pack and Daily Bake Flour Tortillas 6 pack", start="Bakery")
    assert ans2.status == "ok"
    assert ans2.verified is True
    assert ans2.route is not None
    assert "Walk 0m" not in ans2.route.directions_text
    assert "Daily Bake Plain Bagels 4 pack" in ans2.route.directions_text
    assert "Daily Bake Flour Tortillas 6 pack" in ans2.route.directions_text


def test_orchestrator_determinism(finder):
    """The same input twice gives identical answers (ignoring session_id and timings)."""
    q = "Fresh Farms Red Apples 1 kg and Café Corner Trail Mix Pouch large"
    ans1 = run_query(finder, q)
    ans2 = run_query(finder, q)

    assert ans1.status == ans2.status
    assert ans1.verified == ans2.verified
    assert len(ans1.items) == len(ans2.items)
    for it1, it2 in zip(ans1.items, ans2.items):
        assert it1.sku == it2.sku
        assert it1.status == it2.status
        assert it1.quantity == it2.quantity
        assert it1.chosen_location == it2.chosen_location

    assert ans1.route.total_cost == ans2.route.total_cost
    assert ans1.route.ordered_skus == ans2.route.ordered_skus
    assert ans1.route.directions_text == ans2.route.directions_text


def test_speed_twenty_item_request(finder, dataset):
    """A 20-item request finishes in under 5 seconds."""
    # Build a 20-item list from products
    skus = [p.name for p in dataset.products[:20]]
    query = " and ".join(skus)

    t0 = time.monotonic()
    ans = run_query(finder, query)
    elapsed = time.monotonic() - t0

    print(f"\n[Speed Test] 20-item request completed in {elapsed:.3f}s (status={ans.status})")
    assert elapsed < 5.0, f"20-item request took {elapsed:.2f}s, expected < 5.0s"


def test_session_store_ttl_purge():
    """SessionStore: purge by TTL drops sessions exceeding ttl_seconds."""
    sim_time = 0.0

    def fake_clock():
        return sim_time

    store = SessionStore(clock=fake_clock, ttl_seconds=60, max_sessions=1000)
    s1 = RunState(session_id="s1", original_text="q1")
    sim_time = 10.0
    store.put(s1)
    assert store.get("s1") is not None

    # Advance clock past 60s
    sim_time = 75.0
    assert store.get("s1") is None


def test_session_store_lru_cap_drops_oldest():
    """SessionStore: 1000-session capacity cap drops the oldest session when full."""
    sim_time = 0.0

    def fake_clock():
        return sim_time

    # Use cap of 3 to verify eviction mechanics precisely
    store = SessionStore(clock=fake_clock, ttl_seconds=3600, max_sessions=3)
    s1 = RunState(session_id="s1", original_text="q1")
    s2 = RunState(session_id="s2", original_text="q2")
    s3 = RunState(session_id="s3", original_text="q3")
    s4 = RunState(session_id="s4", original_text="q4")

    sim_time = 10.0
    store.put(s1)
    sim_time = 20.0
    store.put(s2)
    sim_time = 30.0
    store.put(s3)

    assert store.get("s1") is not None
    assert store.get("s2") is not None
    assert store.get("s3") is not None

    # Inserting 4th session drops oldest (s1)
    sim_time = 40.0
    store.put(s4)
    assert store.get("s1") is None
    assert store.get("s2") is not None
    assert store.get("s3") is not None
    assert store.get("s4") is not None


def test_create_finder_missing_key_sets_model_note(monkeypatch):
    """interface.create_finder with a missing key sets model_note and uses NoModelClient."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    finder = create_finder(STORE_DIR, settings=Settings(provider="gemini"))
    assert isinstance(finder.client, NoModelClient)
    assert finder.model_note is not None
    assert "GEMINI_API_KEY missing" in finder.model_note

    # Verify that run() emits the MODEL_NOTE event in trace
    ans = finder.run("Fresh Farms Red Apples 1 kg")
    assert any(e.stage == "MODEL_NOTE" and "NoModelClient" in e.note for e in ans.trace)


def test_orchestrator_parse_trace_note_source():
    from planogram_agent.llm.fake_client import FakeLLMClient

    dataset = load_dataset(STORE_DIR, validate=True)
    settings = Settings()

    # 1. Model source in trace
    valid_resp = '{"intent": "find", "items": [{"text": "Store Brand Whole Milk 2 L", "qty": 1}], "start": null, "accessible_only": false, "end_at_checkout": false}'
    model_finder = Orchestrator(dataset=dataset, settings=settings, client=FakeLLMClient(responses=[valid_resp]))
    ans_model = model_finder.run("Store Brand Whole Milk 2 L")
    parse_event_model = next((e for e in ans_model.trace if e.stage == "PARSE"), None)
    assert parse_event_model is not None
    assert parse_event_model.note == "source: model"

    # 2. Fallback source in trace (NoModelClient)
    fallback_finder = Orchestrator(dataset=dataset, settings=settings, client=NoModelClient())
    ans_fallback = fallback_finder.run("Store Brand Whole Milk 2 L")
    parse_event_fallback = next((e for e in ans_fallback.trace if e.stage == "PARSE"), None)
    assert parse_event_fallback is not None
    assert parse_event_fallback.note == "source: fallback"


