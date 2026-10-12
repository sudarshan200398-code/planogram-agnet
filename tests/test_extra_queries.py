"""Report-only evaluation of extra queries to check for overfitting."""
import json
from pathlib import Path

from planogram_agent.data_loader import load_dataset
from planogram_agent.settings import load_settings
from planogram_agent.tools import decide_match, search_products

STORE_DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"
EXTRA_QUERIES_PATH = Path(__file__).resolve().parent / "extra_queries.json"


def test_extra_queries_report():
    """Run extra queries and print pass rates per category (report-only, never fails)."""
    if not EXTRA_QUERIES_PATH.is_file():
        print(f"\nExtra queries file not found at {EXTRA_QUERIES_PATH}")
        return

    dataset = load_dataset(STORE_DEMO_DIR, validate=True)
    settings = load_settings()

    with open(EXTRA_QUERIES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    categories = ["exact", "typo", "synonym", "bare_synonym", "generic", "not_found"]
    results = {}
    failing_cases = {}

    for cat in categories:
        cases = [c for c in data["cases"] if c["category"] == cat]
        passed = 0
        failures = []

        for case in cases:
            case_id = case["id"]
            query = case["query"]
            exp = case["expect"]
            exp_status = exp["status"]
            exp_skus = exp.get("acceptable_skus", [])

            candidates = search_products(query, top_k=settings.top_k, dataset=dataset)
            decision = decide_match(candidates, settings, dataset, query=query)

            if decision.status != exp_status:
                failures.append((
                    case_id,
                    query,
                    f"Status mismatch: expected '{exp_status}', got '{decision.status}'",
                    [(c.sku, c.score) for c in candidates[:3]],
                ))
                continue

            if exp_status == "matched":
                chosen_sku = decision.candidates[0].sku if decision.candidates else None
                if chosen_sku not in exp_skus:
                    failures.append((
                        case_id,
                        query,
                        f"SKU mismatch: expected one of {exp_skus}, got '{chosen_sku}'",
                        [(c.sku, c.score) for c in candidates[:3]],
                    ))
                    continue

            elif exp_status == "ambiguous":
                returned_skus = [c.sku for c in decision.candidates]
                if not all(s in exp_skus for s in returned_skus):
                    failures.append((
                        case_id,
                        query,
                        f"Candidate options not all in acceptable_skus: {returned_skus} vs {exp_skus}",
                        [(c.sku, c.score) for c in candidates[:3]],
                    ))
                    continue

            passed += 1

        total = len(cases)
        rate = (passed / total) * 100.0 if total > 0 else 0.0
        results[cat] = {"passed": passed, "total": total, "rate": rate}
        failing_cases[cat] = failures

    # Print Summary Report
    print("\n" + "=" * 60)
    print("EXTRA QUERIES EVALUATION REPORT (OVERFITTING CHECK)")
    print("=" * 60)
    print(f"{'CATEGORY':<15} | {'PASSED':<8} | {'RATE':<8} | {'STATUS'}")
    print("-" * 60)

    for cat, res in results.items():
        rate = res["rate"]
        passed = res["passed"]
        total = res["total"]
        status = "100%" if rate == 100.0 else f"{rate:.1f}%"
        print(f"{cat:<15} | {passed}/{total:<6} | {rate:>5.1f}%  | {status}")

    print("=" * 60)

    has_failures = any(len(fails) > 0 for fails in failing_cases.values())
    if has_failures:
        print("\nFailing Cases Detail:")
        for cat, fails in failing_cases.items():
            if fails:
                print(f"\n--- {cat} ({len(fails)} failing) ---")
                for item in fails:
                    cid, q, reason, top_cands = item
                    print(f"[{cid}] '{q}': {reason}")
                    print(f"       Top candidates: {top_cands}")
    else:
        print("\nAll 32 extra queries passed successfully (100% generalization rate)!")
    print("=" * 60 + "\n")
