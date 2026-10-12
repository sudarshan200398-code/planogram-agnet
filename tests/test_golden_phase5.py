"""Golden queries evaluation runner for Phase 5 multi-product trip planning."""
from __future__ import annotations

import json
from pathlib import Path

from planogram_agent.data_loader import load_dataset
from planogram_agent.planner import plan_route
from planogram_agent.settings import load_settings
from planogram_agent.tools import resolve_start

STORE_DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"
GOLDEN_QUERIES_PATH = Path(__file__).resolve().parent / "golden_queries.json"

CATEGORIES = ["multi_item", "multi_location", "accessible", "start_point"]


def run_phase5_golden_checks():
    """Run Phase 5 route planning checks against golden_queries.json."""
    dataset = load_dataset(STORE_DEMO_DIR, validate=True)
    settings = load_settings()
    with open(GOLDEN_QUERIES_PATH, "r", encoding="utf-8") as f:
        golden_data = json.load(f)

    results = {}
    failing_cases = {}

    for category in CATEGORIES:
        cases = [c for c in golden_data["cases"] if c["category"] == category]
        passed = 0
        failures = []

        for case in cases:
            case_id = case["id"]
            start_text = case.get("start")
            start_floor = case.get("start_floor")
            accessible_only = case.get("accessible_only", False)
            expected_route = case["expect"]["route"]

            start_node = resolve_start(start_text, dataset, floor=start_floor)
            skus = [item["acceptable_skus"][0] for item in case["expect"]["items"]]

            plan = plan_route(
                dataset,
                start_node,
                skus,
                accessible_only=accessible_only,
                settings=settings,
            )

            # Compare total_cost (within 0.01), floor_changes and connectors_used
            cost_diff = abs(plan.total_cost - expected_route["total_cost"])
            cost_ok = cost_diff <= 0.01 + 1e-9
            fc_ok = plan.floor_changes == expected_route["floor_changes"]
            actual_connectors = [
                c.value if hasattr(c, "value") else str(c) for c in plan.connectors_used
            ]
            conn_ok = actual_connectors == expected_route["connectors_used"]

            if cost_ok and fc_ok and conn_ok:
                passed += 1
            else:
                reasons = []
                if not cost_ok:
                    reasons.append(
                        f"cost expected {expected_route['total_cost']}, got {plan.total_cost} (diff {cost_diff:.4f})"
                    )
                if not fc_ok:
                    reasons.append(
                        f"floor_changes expected {expected_route['floor_changes']}, got {plan.floor_changes}"
                    )
                if not conn_ok:
                    reasons.append(
                        f"connectors expected {expected_route['connectors_used']}, got {actual_connectors}"
                    )
                failures.append((case_id, case.get("query", ""), "; ".join(reasons)))

        total = len(cases)
        pass_rate = (passed / total) * 100.0 if total > 0 else 0.0
        results[category] = {
            "passed": passed,
            "total": total,
            "rate": pass_rate,
        }
        failing_cases[category] = failures

    return results, failing_cases


def test_golden_queries_phase5_runner():
    """Test runner verifying pass rates for Phase 5 categories against golden_queries.json."""
    results, failing_cases = run_phase5_golden_checks()

    # Print summary report
    print("\n" + "=" * 68)
    print(f"{'CATEGORY':<16} | {'PASSED':<8} | {'RATE':<8} | {'STATUS'}")
    print("-" * 68)

    for cat, data in results.items():
        rate = data["rate"]
        passed = data["passed"]
        total = data["total"]
        status = "PASS" if passed == total else "FAIL"
        print(f"{cat:<16} | {passed}/{total:<6} | {rate:>5.1f}%  | {status}")

    print("=" * 68)

    has_failures = any(len(fails) > 0 for fails in failing_cases.values())
    if has_failures:
        print("\nFailing Cases Detail:")
        for cat, fails in failing_cases.items():
            if fails:
                print(f"\n--- {cat} ({len(fails)} failing) ---")
                for cid, q, reason in fails:
                    print(f"[{cid}] '{q}': {reason}")
    else:
        print("\nAll Phase 5 cases passed with 100% success!")

    for cat, data in results.items():
        assert data["passed"] == data["total"], (
            f"Category '{cat}' had {len(failing_cases[cat])} failing cases: {failing_cases[cat]}"
        )
