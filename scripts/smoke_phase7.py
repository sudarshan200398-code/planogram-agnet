"""Smoke script testing Orchestrator, RunState, and Verifier across Phase 7 scenarios."""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to sys.path if not installed in editable mode
repo_root = Path(__file__).resolve().parent.parent
src_dir = repo_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from planogram_agent.interface import answer_question, create_finder, run_query
from planogram_agent.llm.no_model import NoModelClient
from planogram_agent.settings import Settings


def print_answer(scenario_title: str, ans) -> None:
    print("\n" + "=" * 70)
    print(f"SCENARIO: {scenario_title}")
    print("=" * 70)
    print(f"Status:   {ans.status}")
    print(f"Verified: {ans.verified} (repaired={ans.repaired}, rebuilt={ans.rebuilt})")
    stages = [f"{t.stage}{'' if t.ok else '(!)'}" for t in ans.trace]
    print(f"Trace:    {' -> '.join(stages)}")
    if ans.messages:
        print(f"Messages: {ans.messages}")

    print("\nItems:")
    for it in ans.items:
        loc_str = f"node={it.chosen_location.node_id}" if it.chosen_location else "unplaced"
        print(f"  - [{it.index}] '{it.requested}' -> {it.status} (sku={it.sku}, qty={it.quantity}, {loc_str})")
        if it.options:
            opts = ", ".join(f"{o.sku} ({o.name})" for o in it.options)
            print(f"    Options: {opts}")
        if it.reason:
            print(f"    Reason:  {it.reason}")

    if ans.question:
        print(f"\nPending Question for item {ans.question.item_index} ('{ans.question.item_text}'):")
        for o in ans.question.options:
            print(f"  [Option] {o.sku}: {o.name} (score={o.score:.2f})")

    if ans.route:
        print("\nRoute Summary:")
        print(f"  Start: {ans.route.start_label} ({ans.route.start_node})")
        print(f"  Cost:  {ans.route.total_cost}m | Walk: {ans.route.walking_distance}m | Floor changes: {ans.route.floor_changes}")
        print("  Directions:")
        for line in ans.route.directions_text.splitlines():
            print(f"    {line}")
    else:
        print("\nRoute: None")


def main() -> None:
    store_dir = repo_root / "data" / "store_demo"
    settings = Settings()
    finder = create_finder(store_dir, settings=settings, client=NoModelClient())

    # (a) multi-product request across both floors with start near Bakery (full product names)
    qa = "Fresh Farms Red Apples 1 kg and Café Corner Trail Mix Pouch large, I'm near the Bakery"
    ans_a = run_query(finder, qa)
    print_answer("(a) Multi-product across both floors starting near Bakery", ans_a)

    # (b) single word "milk", then answer the question with the first option
    qb = "milk"
    ans_b1 = run_query(finder, qb)
    print_answer("(b.1) Single word 'milk' (expects clarification question)", ans_b1)

    if ans_b1.question and ans_b1.question.options and ans_b1.session_id:
        first_sku = ans_b1.question.options[0].sku
        ans_b2 = answer_question(finder, ans_b1.session_id, ans_b1.question.item_index, first_sku)
        print_answer(f"(b.2) Answer question with first option '{first_sku}'", ans_b2)

    # (c) one out-of-stock item + one item that does not exist + one available item
    qc = "ArtBox Watercolour Paints 12 pack, quantum flux capacitor and Daily Bake Plain Bagels 4 pack"
    ans_c = run_query(finder, qc)
    print_answer("(c) Out-of-stock + Non-existent + Available item", ans_c)

    # (d) step-free request
    qd = "step-free route to Café Corner Trail Mix Pouch large"
    ans_d = run_query(finder, qd)
    print_answer("(d) Step-free accessible route", ans_d)

    # (e) empty text
    qe = "   "
    ans_e = run_query(finder, qe)
    print_answer("(e) Empty text query", ans_e)

    # (f) unknown start place
    qf = "Daily Bake Plain Bagels 4 pack"
    ans_f = run_query(finder, qf, start="Atlantis")
    print_answer("(f) Unknown start place 'Atlantis'", ans_f)


if __name__ == "__main__":
    main()
