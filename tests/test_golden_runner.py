"""Golden queries evaluation runner for Phase 4 lookup tools."""
import json
from pathlib import Path

from planogram_agent.data_loader import load_dataset
from planogram_agent.settings import load_settings
from planogram_agent.tools import (
    check_inventory,
    decide_match,
    resolve_start,
    search_products,
)

STORE_DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"
GOLDEN_QUERIES_PATH = Path(__file__).resolve().parent / "golden_queries.json"

TARGET_PASS_RATES = {
    "exact": 100.0,
    "typo": 90.0,
    "synonym": 90.0,
    "size_narrows": 90.0,
    "generic": 100.0,
    "not_found": 100.0,
    "out_of_stock": 100.0,
    "start_point": 100.0,
}


def run_tool_level_checks():
    """Run all tool-level checks against golden_queries.json and compute stats."""
    dataset = load_dataset(STORE_DEMO_DIR, validate=True)
    settings = load_settings()
    with open(GOLDEN_QUERIES_PATH, "r", encoding="utf-8") as f:
        golden_data = json.load(f)

    results = {}
    failing_cases = {}

    for category, target_rate in TARGET_PASS_RATES.items():
        cases = [c for c in golden_data["cases"] if c["category"] == category]
        passed = 0
        failures = []

        for case in cases:
            case_id = case["id"]
            if category == "start_point":
                start_text = case.get("start")
                start_floor = case.get("start_floor")
                expected_node = case["expect"]["route"]["start_node"]
                try:
                    actual_node = resolve_start(start_text, dataset, floor=start_floor)
                    if actual_node == expected_node:
                        passed += 1
                    else:
                        failures.append((
                            case_id,
                            start_text,
                            f"Expected node '{expected_node}', got '{actual_node}'",
                        ))
                except (ValueError, KeyError, RuntimeError) as exc:
                    failures.append((case_id, start_text, f"Unexpected error: {exc}"))
                continue

            query = case["query"]
            expected_item = case["expect"]["items"][0]
            expected_status = expected_item["status"]
            acceptable_skus = expected_item.get("acceptable_skus", [])
            expected_avail = expected_item.get("availability")

            candidates = search_products(query, top_k=settings.top_k, dataset=dataset)
            decision = decide_match(candidates, settings, dataset, query=query)

            if decision.status != expected_status:
                failures.append((
                    case_id,
                    query,
                    f"Status mismatch: expected '{expected_status}', got '{decision.status}'",
                ))
                continue

            if expected_status == "matched":
                if not decision.candidates or decision.candidates[0].sku not in acceptable_skus:
                    got_sku = decision.candidates[0].sku if decision.candidates else None
                    failures.append((
                        case_id,
                        query,
                        f"SKU mismatch: expected one of {acceptable_skus}, got '{got_sku}'",
                    ))
                    continue

                if expected_avail:
                    chosen_sku = decision.candidates[0].sku
                    actual_avail = check_inventory(chosen_sku, dataset)
                    if actual_avail != expected_avail:
                        failures.append((
                            case_id,
                            query,
                            f"Availability mismatch: expected '{expected_avail}', got '{actual_avail}'",
                        ))
                        continue

            elif expected_status == "ambiguous":
                returned_skus = [cand.sku for cand in decision.candidates]
                if not all(s in acceptable_skus for s in returned_skus):
                    failures.append((
                        case_id,
                        query,
                        f"Candidate options not all in acceptable_skus: {returned_skus} vs {acceptable_skus}",
                    ))
                    continue

            passed += 1

        total = len(cases)
        pass_rate = (passed / total) * 100.0 if total > 0 else 0.0
        results[category] = {
            "passed": passed,
            "total": total,
            "rate": pass_rate,
            "target": target_rate,
        }
        failing_cases[category] = failures

    return results, failing_cases


def test_golden_queries_runner():
    """Test runner verifying pass rates against golden_queries.json."""
    results, failing_cases = run_tool_level_checks()

    # Print summary report
    print("\n" + "=" * 68)
    print(f"{'CATEGORY':<15} | {'PASSED':<8} | {'RATE':<8} | {'TARGET':<8} | {'STATUS'}")
    print("-" * 68)

    for cat, data in results.items():
        rate = data["rate"]
        target = data["target"]
        passed = data["passed"]
        total = data["total"]
        status = "PASS" if rate >= target else "FAIL"
        print(f"{cat:<15} | {passed}/{total:<6} | {rate:>5.1f}%  | {target:>5.1f}%  | {status}")

    print("=" * 68)

    # Print any failing cases
    has_failures = any(len(fails) > 0 for fails in failing_cases.values())
    if has_failures:
        print("\nFailing Cases Detail:")
        for cat, fails in failing_cases.items():
            if fails:
                print(f"\n--- {cat} ({len(fails)} failing) ---")
                for cid, q, reason in fails:
                    print(f"[{cid}] '{q}': {reason}")
    else:
        print("\nAll cases passed with 100% success!")

    # Assert category targets
    for cat, data in results.items():
        assert data["rate"] >= data["target"], (
            f"Category '{cat}' pass rate {data['rate']:.1f}% below target {data['target']:.1f}%"
        )
