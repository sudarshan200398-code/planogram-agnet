"""Report-style test running rule-based fallback over golden_queries.json and extra customer queries."""
from __future__ import annotations

import json
from pathlib import Path

from planogram_agent.agents.query import rule_based_fallback
from planogram_agent.data_loader import load_dataset
from planogram_agent.settings import Settings

STORE_DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"
GOLDEN_QUERIES_PATH = Path(__file__).resolve().parent / "golden_queries.json"
EXTRA_QUERIES_PATH = Path(__file__).resolve().parent / "extra_queries_query_agent.json"

TARGET_RATES = {
    "invalid_input (structural)": 100.0,
    "exact": 95.0,
    "typo": 95.0,
    "synonym": 95.0,
    "size_narrows": 95.0,
    "generic": 95.0,
    "out_of_stock": 95.0,
    "not_found": 95.0,
    "multi_item": 95.0,
    "start_point": 95.0,
    "accessible": 95.0,
    "multi_location": 95.0,
    "mixed": 95.0,
}

STRUCTURAL_INVALID_IDS = {"INV-01", "INV-02", "INV-03", "INV-04"}


def run_fallback_golden_evaluation():
    """Evaluate rule-based fallback across all golden query cases."""
    dataset = load_dataset(STORE_DEMO_DIR, validate=True)
    settings = Settings()
    with open(GOLDEN_QUERIES_PATH, "r", encoding="utf-8") as f:
        golden_data = json.load(f)

    categories: dict[str, list[dict]] = {}
    needs_ai_cases: list[tuple[str, str, str]] = []

    for case in golden_data["cases"]:
        cat = case["category"]
        if cat == "invalid_input":
            if case["id"] in STRUCTURAL_INVALID_IDS:
                categories.setdefault("invalid_input (structural)", []).append(case)
            else:
                # Semantic / adversarial invalid input that requires the AI model path
                res = rule_based_fallback(case["query"], settings, dataset=dataset)
                items_str = [it.text for it in res.items]
                needs_ai_cases.append((
                    case["id"],
                    case["query"],
                    f"intent='{res.intent}', items={items_str}",
                ))
        else:
            categories.setdefault(cat, []).append(case)

    results: dict[str, dict] = {}
    failures: dict[str, list[tuple[str, str, str]]] = {}

    for cat, cases in categories.items():
        passed = 0
        cat_fails: list[tuple[str, str, str]] = []
        target = TARGET_RATES.get(cat, 95.0)

        for case in cases:
            case_id = case["id"]
            query = case["query"]
            res = rule_based_fallback(query, settings, dataset=dataset)

            if cat == "invalid_input (structural)":
                if res.intent == "unknown":
                    passed += 1
                else:
                    cat_fails.append((
                        case_id,
                        query,
                        f"Expected intent 'unknown', got '{res.intent}' with items {[i.text for i in res.items]}",
                    ))
                continue

            expected_items = [it["text"] for it in case["expect"].get("items", [])]
            expected_start = case.get("start")
            expected_acc = case.get("accessible_only", False)

            actual_items = [it.text for it in res.items]
            items_ok = actual_items == expected_items
            start_ok = res.start == expected_start
            acc_ok = res.accessible_only == expected_acc

            if items_ok and start_ok and acc_ok:
                passed += 1
            else:
                reasons: list[str] = []
                if not items_ok:
                    reasons.append(f"items: expected {expected_items}, got {actual_items}")
                if not start_ok:
                    reasons.append(f"start: expected {expected_start}, got {res.start}")
                if not acc_ok:
                    reasons.append(f"accessible: expected {expected_acc}, got {res.accessible_only}")
                cat_fails.append((case_id, query, "; ".join(reasons)))

        rate = (passed / len(cases)) * 100.0 if cases else 0.0
        results[cat] = {
            "passed": passed,
            "total": len(cases),
            "rate": rate,
            "target": target,
        }
        failures[cat] = cat_fails

    return results, failures, needs_ai_cases


def test_golden_queries_phase6a_fallback():
    """Verify rule-based fallback match rates per category against golden_queries.json."""
    results, failures, needs_ai_cases = run_fallback_golden_evaluation()

    print("\n" + "=" * 76)
    print(f"{'CATEGORY':<28} | {'PASSED':<8} | {'RATE':<8} | {'TARGET':<8} | {'STATUS'}")
    print("-" * 76)

    for cat, data in results.items():
        rate = data["rate"]
        target = data["target"]
        passed = data["passed"]
        total = data["total"]
        status = "PASS" if rate >= target else "FAIL"
        print(f"{cat:<28} | {passed}/{total:<6} | {rate:>5.1f}%  | {target:>5.1f}%  | {status}")

    print("=" * 76)

    # Print "needs the AI model path" report-only section
    print("\nneeds the AI model path (report-only):")
    print("-" * 76)
    for cid, query, actual_return in needs_ai_cases:
        print(f"[{cid}] {query!r} -> fallback returned {actual_return}")
    print("-" * 76)

    has_failures = any(len(f) > 0 for f in failures.values())
    if has_failures:
        print("\nFailing Cases Detail:")
        for cat, fails in failures.items():
            if fails:
                print(f"\n--- {cat} ({len(fails)} failing) ---")
                for cid, q, reason in fails:
                    print(f"[{cid}] '{q}': {reason}")
    else:
        print("\nAll tested golden query categories passed targets with 100% success!")

    for cat, data in results.items():
        assert data["rate"] >= data["target"], (
            f"Category '{cat}' pass rate {data['rate']:.1f}% below target {data['target']:.1f}%"
        )


def test_extra_queries_overfitting_report():
    """Report-only evaluation of rule-based fallback on 30 diverse customer queries."""
    if not EXTRA_QUERIES_PATH.is_file():
        return

    dataset = load_dataset(STORE_DEMO_DIR, validate=True)
    settings = Settings()
    with open(EXTRA_QUERIES_PATH, "r", encoding="utf-8") as f:
        extra_data = json.load(f)

    types: dict[str, list[dict]] = {}
    for case in extra_data["cases"]:
        types.setdefault(case["type"], []).append(case)

    results: dict[str, dict] = {}
    failures: dict[str, list[tuple[str, str, str]]] = {}

    for qtype, cases in types.items():
        passed = 0
        type_fails: list[tuple[str, str, str]] = []

        for case in cases:
            case_id = case["id"]
            query = case["query"]
            res = rule_based_fallback(query, settings, dataset=dataset)

            expected_items = case["expect"].get("items", [])
            expected_start = case["expect"].get("start")
            expected_acc = case["expect"].get("accessible_only", False)

            actual_items = [{"text": it.text, "qty": it.qty} for it in res.items]
            items_ok = actual_items == expected_items
            start_ok = res.start == expected_start
            acc_ok = res.accessible_only == expected_acc

            if items_ok and start_ok and acc_ok:
                passed += 1
            else:
                reasons: list[str] = []
                if not items_ok:
                    reasons.append(f"items: expected {expected_items}, got {actual_items}")
                if not start_ok:
                    reasons.append(f"start: expected {expected_start}, got {res.start}")
                if not acc_ok:
                    reasons.append(f"accessible: expected {expected_acc}, got {res.accessible_only}")
                type_fails.append((case_id, query, "; ".join(reasons)))

        rate = (passed / len(cases)) * 100.0 if cases else 0.0
        results[qtype] = {
            "passed": passed,
            "total": len(cases),
            "rate": rate,
        }
        failures[qtype] = type_fails

    print("\n" + "=" * 76)
    print("EXTRA QUERIES OVERFITTING CHECK (REPORT-ONLY)")
    print("=" * 76)
    print(f"{'PHRASING TYPE':<32} | {'PASSED':<8} | {'RATE':<8}")
    print("-" * 76)

    total_passed = sum(d["passed"] for d in results.values())
    total_cases = sum(d["total"] for d in results.values())

    for qtype, data in results.items():
        rate = data["rate"]
        passed = data["passed"]
        total = data["total"]
        print(f"{qtype:<32} | {passed}/{total:<6} | {rate:>5.1f}%")

    print("-" * 76)
    overall_rate = (total_passed / total_cases) * 100.0 if total_cases else 0.0
    print(f"{'OVERALL':<32} | {total_passed}/{total_cases:<6} | {overall_rate:>5.1f}%")
    print("=" * 76)

    print("\nExtra Queries Failing Cases Detail:")
    print("-" * 76)
    has_any_fail = False
    for qtype, fails in failures.items():
        if fails:
            has_any_fail = True
            print(f"\n--- {qtype} ({len(fails)} failing) ---")
            for cid, q, reason in fails:
                print(f"[{cid}] '{q}':\n  -> {reason}")
    if not has_any_fail:
        print("No failures encountered.")
    print("-" * 76)
