#!/usr/bin/env python3
"""Live check script for evaluating Gemini integration with the Planogram Agent.

Run manually in terminal with GEMINI_API_KEY set:
    set GEMINI_API_KEY=your_key_here   (Windows cmd)
    $env:GEMINI_API_KEY="your_key_here" (Windows PowerShell)
    python scripts\\live_check.py

NOTE: Transmits test sentences to Google.
"""
from __future__ import annotations

import datetime
import importlib.metadata
import json
import os
import re
import sys
import time
from pathlib import Path

# Add project root to sys.path so planogram_agent can be imported
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from planogram_agent.agents.query import parse_request, rule_based_fallback
from planogram_agent.data_loader import load_dataset
from planogram_agent.interface import create_finder
from planogram_agent.llm.gemini_client import GeminiClient
from planogram_agent.llm.no_model import QuotaExhaustedError
from planogram_agent.settings import Settings, load_settings

def _compute_max_api_calls() -> int:
    env_cap = os.environ.get("LIVE_CHECK_MAX_CALLS")
    if env_cap:
        try:
            return min(int(env_cap), 60)
        except ValueError:
            pass
    return 18

MAX_API_CALLS = _compute_max_api_calls()
total_api_calls = 0


class CallCapExceeded(Exception):
    """Raised when the model calls limit is reached."""
    pass


def on_sdk_call() -> None:
    """Callback invoked before every SDK call to Gemini."""
    global total_api_calls
    if total_api_calls >= MAX_API_CALLS:
        raise CallCapExceeded(f"Reached maximum limit of {MAX_API_CALLS} Gemini API calls.")
    total_api_calls += 1


def redact(text: str) -> str:
    """Redact sensitive API keys from text."""
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        text = text.replace(key, "***REDACTED***")
    text = re.sub(r"AIza[0-9A-Za-z_-]{35}", "***REDACTED***", text)
    return text


class ReportLogger:
    """Logger that prints to stdout and writes to a file, redacting every line."""

    def __init__(self, filepath: Path) -> None:
        self.filepath = filepath
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(self.filepath, "w", encoding="utf-8")

    def print(self, *args, **kwargs) -> None:
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        raw_text = sep.join(str(a) for a in args)
        redacted_text = redact(raw_text)
        sys.stdout.write(redacted_text + end)
        sys.stdout.flush()
        self.file.write(redacted_text + end)
        self.file.flush()

    def close(self) -> None:
        self.file.close()


def list_flash_models(api_key: str) -> list[str] | None:
    """Query SDK for models containing 'flash'."""
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        models_pager = client.models.list()
        flash_models: list[str] = []
        for m in models_pager:
            name = getattr(m, "name", "") or ""
            display_name = getattr(m, "display_name", "") or ""
            if "flash" in name.lower() or "flash" in display_name.lower():
                cleaned = name.removeprefix("models/") if name.startswith("models/") else name
                flash_models.append(cleaned)
        return flash_models
    except Exception:
        return None


def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.stderr.write(
            "Error: GEMINI_API_KEY environment variable is not set.\n"
            "Please set GEMINI_API_KEY and run again:\n"
            "  Windows PowerShell: $env:GEMINI_API_KEY=\"your_key\"\n"
            "  Windows CMD:        set GEMINI_API_KEY=your_key\n"
        )
        sys.exit(1)

    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"live_check_{now_str}.txt"
    report_path = REPO_ROOT / "reports" / report_filename
    logger = ReportLogger(report_path)

    seen_exception_types: set[str] = set()
    seen_distinct_errors: set[str] = set()
    quota_exhausted = False

    def log_distinct_error(prefix: str, exc: Exception) -> None:
        nonlocal quota_exhausted
        exc_type = type(exc).__name__
        seen_exception_types.add(exc_type)
        redacted_msg = redact(str(exc))
        err_sig = f"{exc_type}: {redacted_msg}"
        if err_sig not in seen_distinct_errors:
            seen_distinct_errors.add(err_sig)
            logger.print(f"[{prefix}] Exception: {exc_type}: {redacted_msg}")
        if isinstance(exc, QuotaExhaustedError):
            retry_s = getattr(exc, "retry_after_seconds", None)
            n_min = max(1, int(round(retry_s / 60))) if retry_s else 10
            logger.print(f"Stopped: quota exhausted (retry in {n_min} min)")
            quota_exhausted = True

    try:
        settings = load_settings()
        holdout_path = REPO_ROOT / "tests" / "holdout_queries_query_agent_v2.json"
        with open(holdout_path, "r", encoding="utf-8") as f:
            holdout_data = json.load(f)
        holdout_cases = holdout_data.get("cases", [])

        # Start info banner
        try:
            genai_version = importlib.metadata.version("google-genai")
        except Exception:
            genai_version = "unknown"

        logger.print("=" * 76)
        logger.print("PLANOGRAM AGENT - LIVE CHECK")
        logger.print("=" * 76)
        logger.print(f"Model Name:             {settings.model_name}")
        logger.print(f"Provider:               {settings.provider}")
        logger.print(f"google-genai Version:   {genai_version}")
        logger.print(f"model_timeout_seconds:  {settings.model_timeout_seconds}")
        logger.print(f"Total Call Cap:         {MAX_API_CALLS}")
        logger.print(f"Holdout Messages Count: {len(holdout_cases)}")
        logger.print(f"Report Log File:        {report_path.resolve()}")
        logger.print("=" * 76)
        logger.print()

        store_path = REPO_ROOT / "data" / "store_demo"
        dataset = load_dataset(store_path, validate=True)
        part_a_settings = settings.model_copy(update={"model_timeout_seconds": max(20.0, float(settings.model_timeout_seconds))})
        client = GeminiClient(settings=part_a_settings, api_key=api_key, on_call=on_sdk_call)

        # ------------------------------------------------------------------
        # PART B: End-to-end Orchestrator requests (Run FIRST)
        # ------------------------------------------------------------------
        logger.print("--- PART B: END-TO-END ORCHESTRATOR REQUESTS ---")
        finder = create_finder(store_path, settings=settings, client=client)

        in_stock_skus = {inv.sku for inv in dataset.inventory if inv.quantity > 0}
        sku_to_locs: dict[str, list] = {}
        for loc in dataset.planogram:
            sku_to_locs.setdefault(loc.sku, []).append(loc)

        l1_prods = [
            p for p in dataset.products
            if p.sku in in_stock_skus and len(sku_to_locs.get(p.sku, [])) == 1 and sku_to_locs[p.sku][0].floor == 1
        ]
        l2_prods = [
            p for p in dataset.products
            if p.sku in in_stock_skus and len(sku_to_locs.get(p.sku, [])) == 1 and sku_to_locs[p.sku][0].floor == 2
        ]

        def print_ans_summary(label: str, query_text: str, ans) -> None:
            logger.print(f"\n>> Scenario: {label}")
            logger.print(f"Query:        {query_text}")
            logger.print(f"Answer Status: {ans.status}")
            parse_event = next((e for e in ans.trace if e.stage == "PARSE"), None)
            parse_note = parse_event.note if parse_event else "No PARSE stage recorded"
            logger.print(f"PARSE Note:   {parse_note}")
            logger.print("Items:")
            for it in ans.items:
                logger.print(
                    f"  - [{it.status}] '{it.requested}' -> {it.name or 'None'} "
                    f"(SKU: {it.sku}, Qty: {it.quantity})"
                )
            if ans.route and ans.route.directions_text:
                logger.print(f"Route Text:\n{ans.route.directions_text}")
            else:
                logger.print("Route Text:   No route generated")

        try:
            # (a) Multi-product across both floors with start point
            if total_api_calls < MAX_API_CALLS and not quota_exhausted:
                time.sleep(2.0)
                p1 = l1_prods[0]
                p2 = l2_prods[0]
                logger.print(
                    f"Choosing L1 product '{p1.name}' (SKU: {p1.sku}, single location on Floor 1, in-stock) "
                    f"and L2 product '{p2.name}' (SKU: {p2.sku}, single location on Floor 2, in-stock)."
                )
                q_a = f"{p1.name} and {p2.name}, I'm near the Bakery"
                ans_a = finder.run(q_a)
                print_ans_summary("(a) Multi-product across both floors with start point", q_a, ans_a)
                if ans_a.status == "error" and any("quota" in m.lower() for m in ans_a.messages):
                    logger.print("Stopped: quota exhausted (retry in 10 min)")
                    quota_exhausted = True

            # (b) "milk" then answer question with options[0]
            if total_api_calls < MAX_API_CALLS and not quota_exhausted:
                time.sleep(2.0)
                logger.print("Executing ambiguous query 'milk' to trigger clarification flow.")
                ans_b1 = finder.run("milk")
                print_ans_summary("(b.1) Ambiguous 'milk' request", "milk", ans_b1)

                if ans_b1.question and ans_b1.question.options:
                    chosen_opt = ans_b1.question.options[0]
                    logger.print(
                        f"Clarification question received for item index {ans_b1.question.item_index}. "
                        f"Selecting options[0]: '{chosen_opt.name}' (SKU: {chosen_opt.sku})."
                    )
                    time.sleep(2.0)
                    ans_b2 = finder.answer_question(
                        ans_b1.session_id,
                        ans_b1.question.item_index,
                        chosen_opt.sku,
                    )
                    print_ans_summary("(b.2) Answer question with options[0]", f"SKU {chosen_opt.sku}", ans_b2)

            # (c) Out of stock + not found + available
            if total_api_calls < MAX_API_CALLS and not quota_exhausted:
                time.sleep(2.0)
                oos_sku = next(inv.sku for inv in dataset.inventory if inv.quantity == 0)
                oos_prod = next(p for p in dataset.products if p.sku == oos_sku)
                invented_name = "Galactic Ray Gun 3000"
                avail_prod = l1_prods[1] if len(l1_prods) > 1 else l1_prods[0]
                logger.print(
                    f"Choosing out-of-stock product '{oos_prod.name}' (SKU: {oos_prod.sku}, quantity == 0), "
                    f"invented product '{invented_name}' (verified not in catalogue), "
                    f"and available product '{avail_prod.name}' (SKU: {avail_prod.sku}, quantity > 0)."
                )
                q_c = f"{oos_prod.name}, {invented_name}, and {avail_prod.name}"
                ans_c = finder.run(q_c)
                print_ans_summary("(c) Out of stock + not found + available", q_c, ans_c)

            # (d) Step-free Level 2 product
            if total_api_calls < MAX_API_CALLS and not quota_exhausted:
                time.sleep(2.0)
                step_free_prod = l2_prods[0]
                logger.print(
                    f"Choosing Level 2 product '{step_free_prod.name}' (SKU: {step_free_prod.sku}) "
                    f"for step-free accessible navigation."
                )
                q_d = f"wheelchair accessible route to {step_free_prod.name}"
                ans_d = finder.run(q_d)
                print_ans_summary("(d) Step-free Level 2 request", q_d, ans_d)
                if ans_d.route:
                    connectors = [c.lower() for c in ans_d.route.connectors_used]
                    assert not any("stairs" in c or "escalator" in c for c in connectors), (
                        f"Accessible route used non-accessible connector: {ans_d.route.connectors_used}"
                    )
                    logger.print(
                        f"Verified: route connectors used ({ans_d.route.connectors_used}) contain no stairs or escalators."
                    )

            # (e) Casual sentence with polite wrapper
            if total_api_calls < MAX_API_CALLS and not quota_exhausted:
                time.sleep(2.0)
                casual_prod = l1_prods[0]
                logger.print(
                    f"Choosing product '{casual_prod.name}' (SKU: {casual_prod.sku}) wrapped in polite greeting."
                )
                q_e = f"Good morning! Could you please help me find {casual_prod.name}? Thank you so much!"
                ans_e = finder.run(q_e)
                print_ans_summary("(e) Casual sentence with polite wrapper", q_e, ans_e)

        except QuotaExhaustedError as qee:
            log_distinct_error("Part B", qee)
        except CallCapExceeded as cce:
            logger.print(f"\n[ABORT] {cce}")
        except Exception as exc:
            log_distinct_error("Part B", exc)

        logger.print()

        # ------------------------------------------------------------------
        # PART A: Holdout v2 queries evaluation in round-robin until cap
        # ------------------------------------------------------------------
        logger.print("--- PART A: HOLDOUT V2 QUERIES EVALUATION ---")
        model_results = []
        fallback_results = []
        fallback_reasons: dict[str, int] = {}
        model_latencies: list[float] = []
        failing_cases: list[dict] = []

        type_cases: dict[str, list[dict]] = {}
        for c in holdout_cases:
            type_cases.setdefault(c.get("type", "general"), []).append(c)

        # Build round-robin case list across message types
        round_robin_cases: list[dict] = []
        queues = {qtype: list(cases) for qtype, cases in type_cases.items()}
        while any(queues.values()):
            for qtype in list(queues.keys()):
                if queues[qtype]:
                    round_robin_cases.append(queues[qtype].pop(0))

        first_call_done = False

        for idx, case in enumerate(round_robin_cases):
            if quota_exhausted:
                break

            if total_api_calls >= MAX_API_CALLS:
                logger.print(f"\n[ABORT] Reached API call cap ({MAX_API_CALLS}).")
                break

            cid = case["id"]
            qtype = case.get("type", "general")
            query = case["query"]
            expect = case["expect"]
            expected_items = expect.get("items", [])
            expected_start = expect.get("start")
            expected_acc = expect.get("accessible_only", False)

            if idx > 0:
                time.sleep(2.0)

            t0 = time.monotonic()
            try:
                res = parse_request(query, client, part_a_settings, dataset=dataset)
                elapsed = time.monotonic() - t0
                first_call_done = True
                if res.fallback_reason == "quota_exhausted":
                    logger.print("Stopped: quota exhausted (retry in 10 min)")
                    quota_exhausted = True
            except QuotaExhaustedError as qee:
                elapsed = time.monotonic() - t0
                log_distinct_error(cid, qee)
                res = rule_based_fallback(query, part_a_settings, dataset=dataset, fallback_reason="quota_exhausted")
            except CallCapExceeded as cce:
                logger.print(f"\n[ABORT] {cce}")
                break
            except Exception as exc:
                elapsed = time.monotonic() - t0
                log_distinct_error(cid, exc)
                if not first_call_done:
                    err_lower = str(exc).lower()
                    if "not found" in err_lower or "404" in err_lower:
                        logger.print("\n[!] The first call failed with 'model not found'.")
                        flash_models = list_flash_models(api_key)
                        if flash_models:
                            logger.print("Available models matching 'flash':")
                            for fm in flash_models:
                                logger.print(f"  - {fm}")
                        return
                first_call_done = True
                res = rule_based_fallback(query, part_a_settings, dataset=dataset, fallback_reason="model_unavailable")

            actual_items = [{"text": it.text, "qty": it.qty} for it in res.items]
            items_ok = actual_items == expected_items
            start_ok = res.start == expected_start
            acc_ok = res.accessible_only == expected_acc
            overall_ok = items_ok and start_ok and acc_ok

            if res.source == "model":
                model_results.append((cid, qtype, overall_ok))
                model_latencies.append(elapsed)
            else:
                fallback_results.append((cid, qtype, overall_ok))
                reason_key = res.fallback_reason or "unknown"
                fallback_reasons[reason_key] = fallback_reasons.get(reason_key, 0) + 1

            if not overall_ok:
                failing_cases.append({
                    "id": cid,
                    "type": qtype,
                    "query": query,
                    "source": res.source,
                    "fallback_reason": res.fallback_reason,
                    "expected_items": expected_items,
                    "actual_items": actual_items,
                    "expected_start": expected_start,
                    "actual_start": res.start,
                    "expected_acc": expected_acc,
                    "actual_acc": res.accessible_only,
                })

            src_label = f"model ({elapsed:.2f}s)" if res.source == "model" else f"fallback ({res.fallback_reason})"
            status_label = "PASS" if overall_ok else "FAIL"
            logger.print(f"[{cid}] {status_label:<4} | source: {src_label:<25} | query: {query}")

        logger.print()

        # ------------------------------------------------------------------
        # SUMMARY BLOCK
        # ------------------------------------------------------------------
        logger.print("\n" + "=" * 76)
        logger.print("SUMMARY")
        logger.print("=" * 76)
        total_holdout = len(holdout_cases)
        model_count = len(model_results)
        fallback_count = len(fallback_results)

        logger.print(f"Total API Calls Used:     {total_api_calls} / {MAX_API_CALLS}")
        logger.print(f"Model-Sourced Results:    {model_count} / {total_holdout}")
        logger.print(f"Fallback Results:         {fallback_count} / {total_holdout}")
        logger.print("Fallback Reasons Count:")
        if fallback_reasons:
            for r_name, r_cnt in sorted(fallback_reasons.items()):
                logger.print(f"  - {r_name:<20}: {r_cnt}")
        else:
            logger.print("  (none - all queries answered by model)")

        if model_count == 0:
            logger.print("\nNOT MEASURED: the model produced no results")
        else:
            model_passed = sum(1 for _, _, ok in model_results if ok)
            model_rate = (model_passed / model_count * 100.0) if model_count > 0 else 0.0
            logger.print(f"\nModel Pass Rate (overall): {model_rate:.1f}% ({model_passed}/{model_count})")

            logger.print("\nModel Pass Rate per Type:")
            logger.print(f"{'TYPE':<25} | {'PASSED':<10} | {'RATE':<8}")
            logger.print("-" * 50)
            for qtype, cases in sorted(type_cases.items()):
                type_cids = {c["id"] for c in cases}
                t_model = [ok for cid, t, ok in model_results if cid in type_cids]
                t_model_passed = sum(1 for ok in t_model if ok)
                t_rate_str = f"{(t_model_passed / len(t_model) * 100.0):.1f}%" if t_model else "N/A (0)"
                logger.print(f"{qtype:<25} | {t_model_passed}/{len(t_model):<8} | {t_rate_str}")

        # Rule-based fallback pass rate on same cases
        fb_passed_total = 0
        fb_type_stats: dict[str, list[bool]] = {}
        for c in holdout_cases:
            fbr = rule_based_fallback(c["query"], part_a_settings, dataset=dataset)
            act_it = [{"text": it.text, "qty": it.qty} for it in fbr.items]
            exp_it = c["expect"].get("items", [])
            f_ok = (
                act_it == exp_it
                and fbr.start == c["expect"].get("start")
                and fbr.accessible_only == c["expect"].get("accessible_only", False)
            )
            if f_ok:
                fb_passed_total += 1
            fb_type_stats.setdefault(c.get("type", "general"), []).append(f_ok)

        fb_overall_rate = (fb_passed_total / total_holdout * 100.0) if total_holdout > 0 else 0.0
        logger.print(f"\nRule-Based Fallback Pass Rate (comparison): {fb_overall_rate:.1f}% ({fb_passed_total}/{total_holdout})")
        logger.print("\nRule-Based Fallback Pass Rate per Type:")
        logger.print(f"{'TYPE':<25} | {'PASSED':<10} | {'RATE':<8}")
        logger.print("-" * 50)
        for qtype, results_list in sorted(fb_type_stats.items()):
            p_cnt = sum(1 for ok in results_list if ok)
            rate_str = f"{(p_cnt / len(results_list) * 100.0):.1f}%"
            logger.print(f"{qtype:<25} | {p_cnt}/{len(results_list):<8} | {rate_str}")

        # Latency
        if model_latencies:
            avg_lat = sum(model_latencies) / len(model_latencies)
            max_lat = max(model_latencies)
            logger.print(f"\nAverage Model Call Latency: {avg_lat:.2f}s")
            logger.print(f"Maximum Model Call Latency: {max_lat:.2f}s")
        else:
            logger.print("\nModel Latencies: N/A (no model calls succeeded)")

        # Failing cases details
        if failing_cases:
            logger.print("\n--- FAILING CASES DETAIL ---")
            for fc in failing_cases:
                logger.print(f"\n[{fc['id']}] ({fc['type']})")
                logger.print(f"  Query:           {fc['query']}")
                logger.print(f"  Source:          {fc['source']} (fallback_reason: {fc['fallback_reason']})")
                logger.print(f"  Expected Items:  {fc['expected_items']}")
                logger.print(f"  Actual Items:    {fc['actual_items']}")
                logger.print(f"  Expected Start:  {fc['expected_start']} | Actual: {fc['actual_start']}")
                logger.print(f"  Expected Acc:    {fc['expected_acc']} | Actual: {fc['actual_acc']}")
        else:
            logger.print("\nFailing Cases: None! All cases passed expected checks.")

        # Exceptions seen
        logger.print(f"\nExceptions Encountered: {', '.join(sorted(seen_exception_types)) if seen_exception_types else 'None'}")
        logger.print("=" * 76)
        logger.print(f"Log output written to: {report_path.resolve()}")
        logger.print("=" * 76)

    finally:
        logger.close()


if __name__ == "__main__":
    main()
