"""Comprehensive tests for the Verifier, problem codes, repair/rebuild paths, and boundaries."""
from __future__ import annotations

import ast
from pathlib import Path
import pytest

from planogram_agent.agents.verifier import (
    compute_expected_status,
    repair_answer,
    verify_answer,
)
from planogram_agent.data_loader import load_dataset
from planogram_agent.interface import create_finder, run_query
from planogram_agent.llm.no_model import NoModelClient
from planogram_agent.runtime.orchestrator import Orchestrator, compose_answer
from planogram_agent.runtime.rebuild import rebuild_answer
from planogram_agent.runtime.state import Answer, ItemResult, Question, RouteSummary, RunState
from planogram_agent.matching import Candidate
from planogram_agent.schemas import ConnectorType
from planogram_agent.settings import Settings
from planogram_agent.tools import Location

STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"
VERIFIER_PATH = Path(__file__).resolve().parent.parent / "src" / "planogram_agent" / "agents" / "verifier.py"
REBUILD_PATH = Path(__file__).resolve().parent.parent / "src" / "planogram_agent" / "runtime" / "rebuild.py"


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(STORE_DIR, validate=True)


@pytest.fixture(scope="module")
def settings():
    return Settings()


@pytest.fixture(scope="module")
def finder(dataset, settings):
    return create_finder(STORE_DIR, settings=settings, client=NoModelClient())


def test_valid_answer_gives_ok(finder, dataset, settings):
    """A valid answer passes verification with verdict.ok == True and no problems."""
    ans = run_query(finder, "Fresh Farms Red Apples 1 kg")
    assert ans.status == "ok"
    assert ans.verified is True

    # Run verify_answer directly
    state = RunState(session_id="s_test", original_text="Fresh Farms Red Apples 1 kg")
    state.parsed_request = finder.run("Fresh Farms Red Apples 1 kg").route  # dummy state
    # Use real answer from run_query
    # Construct matching state
    from planogram_agent.agents.query import ParsedItem, ParsedRequest
    state.parsed_request = ParsedRequest(
        raw_text="Fresh Farms Red Apples 1 kg",
        intent="find",
        items=[ParsedItem(text="Fresh Farms Red Apples 1 kg", qty=1)],
    )

    from planogram_agent.agents.routing import plan_trip
    state.start = "Entrance"
    state.start_node = "L1_ENTRANCE"
    state.routing_result = plan_trip(dataset, start_text="Entrance", skus=["PRO-APP-001"], settings=settings)

    verdict = verify_answer(ans, state, dataset, settings)
    assert verdict.ok is True
    assert len(verdict.problems) == 0


def test_verifier_detects_unknown_sku(dataset, settings):
    """Problem code UNKNOWN_SKU when answer references an invented SKU."""
    ans = Answer(
        status="ok",
        items=[
            ItemResult(
                index=0,
                requested="Bogus Item",
                status="available",
                sku="NON-EXISTENT-SKU-999",
                name="Bogus Item Name",
                quantity=10,
                chosen_location=Location(floor=1, zone="Produce", bay="A", shelf_level=1, node_id="L1_PRODUCE"),
            )
        ],
    )
    state = RunState(session_id="s", original_text="Bogus Item")
    verdict = verify_answer(ans, state, dataset, settings)
    codes = {p.code for p in verdict.problems}
    assert "UNKNOWN_SKU" in codes


def test_verifier_detects_name_mismatch(dataset, settings):
    """Problem code NAME_MISMATCH when item name does not match catalogue."""
    ans = Answer(
        status="ok",
        items=[
            ItemResult(
                index=0,
                requested="Fresh Farms Red Apples 1 kg",
                status="available",
                sku="PRO-APP-001",
                name="Wrong Product Name",
                quantity=51,
                chosen_location=Location(floor=1, zone="Produce", bay="C", shelf_level=3, node_id="L1_PRODUCE"),
            )
        ],
    )
    state = RunState(session_id="s", original_text="Fresh Farms Red Apples 1 kg")
    verdict = verify_answer(ans, state, dataset, settings)
    codes = {p.code for p in verdict.problems}
    assert "NAME_MISMATCH" in codes


def test_verifier_detects_stock_mismatch(dataset, settings):
    """Problem code STOCK_MISMATCH when stock quantity or status is wrong."""
    ans = Answer(
        status="ok",
        items=[
            ItemResult(
                index=0,
                requested="Fresh Farms Red Apples 1 kg",
                status="available",
                sku="PRO-APP-001",
                name="Fresh Farms Red Apples 1 kg",
                quantity=9999,  # actual quantity is 51
                chosen_location=Location(floor=1, zone="Produce", bay="C", shelf_level=3, node_id="L1_PRODUCE"),
            )
        ],
    )
    state = RunState(session_id="s", original_text="Fresh Farms Red Apples 1 kg")
    verdict = verify_answer(ans, state, dataset, settings)
    codes = {p.code for p in verdict.problems}
    assert "STOCK_MISMATCH" in codes


def test_verifier_detects_location_mismatch(dataset, settings):
    """Problem code LOCATION_MISMATCH when bay or shelf level is wrong."""
    ans = Answer(
        status="ok",
        items=[
            ItemResult(
                index=0,
                requested="Fresh Farms Red Apples 1 kg",
                status="available",
                sku="PRO-APP-001",
                name="Fresh Farms Red Apples 1 kg",
                quantity=51,
                chosen_location=Location(floor=1, zone="Produce", bay="Z", shelf_level=99, node_id="L1_PRODUCE"),
            )
        ],
    )
    state = RunState(session_id="s", original_text="Fresh Farms Red Apples 1 kg")
    verdict = verify_answer(ans, state, dataset, settings)
    codes = {p.code for p in verdict.problems}
    assert "LOCATION_MISMATCH" in codes


def test_verifier_detects_item_not_accounted(dataset, settings):
    """Problem code ITEM_NOT_ACCOUNTED when a requested item is missing in answer."""
    from planogram_agent.agents.query import ParsedItem, ParsedRequest

    state = RunState(
        session_id="s",
        original_text="apples and bananas",
        parsed_request=ParsedRequest(
            raw_text="apples and bananas",
            intent="find",
            items=[ParsedItem(text="apples", qty=1), ParsedItem(text="bananas", qty=1)],
        ),
    )
    # Answer only accounts for 1 item
    ans = Answer(
        status="partial",
        items=[
            ItemResult(
                index=0,
                requested="apples",
                status="available",
                sku="PRO-APP-001",
                name="Fresh Farms Red Apples 1 kg",
                quantity=51,
                chosen_location=Location(floor=1, zone="Produce", bay="C", shelf_level=3, node_id="L1_PRODUCE"),
            )
        ],
    )
    verdict = verify_answer(ans, state, dataset, settings)
    codes = {p.code for p in verdict.problems}
    assert "ITEM_NOT_ACCOUNTED" in codes


def test_verifier_detects_route_item_invalid(finder, dataset, settings):
    """Problem code ROUTE_ITEM_INVALID when route contains an unavailable product."""
    ans = run_query(finder, "Fresh Farms Red Apples 1 kg")
    # Tamper route to include an out-of-stock product
    assert ans.route is not None
    ans.route.ordered_skus.append("TOY-ART-005")  # out of stock item
    state = RunState(session_id="s", original_text="Fresh Farms Red Apples 1 kg")
    verdict = verify_answer(ans, state, dataset, settings)
    codes = {p.code for p in verdict.problems}
    assert "ROUTE_ITEM_INVALID" in codes


def test_verifier_detects_leg_cost_and_total_mismatch(finder, dataset, settings):
    """Problem codes LEG_COST_MISMATCH and TOTAL_MISMATCH."""
    from planogram_agent.agents.query import ParsedItem, ParsedRequest
    from planogram_agent.agents.routing import plan_trip

    state = RunState(
        session_id="s",
        original_text="Fresh Farms Red Apples 1 kg",
        parsed_request=ParsedRequest(
            raw_text="Fresh Farms Red Apples 1 kg",
            intent="find",
            items=[ParsedItem(text="Fresh Farms Red Apples 1 kg", qty=1)],
        ),
        start="Entrance",
        start_node="L1_ENTRANCE",
    )
    r_res = plan_trip(dataset, start_text="Entrance", skus=["PRO-APP-001"], settings=settings)
    state.routing_result = r_res

    ans = run_query(finder, "Fresh Farms Red Apples 1 kg")
    assert ans.route is not None

    # Tamper leg cost
    state.routing_result.trip_plan.legs[0].total_cost = 999.0
    verdict_leg = verify_answer(ans, state, dataset, settings)
    codes_leg = {p.code for p in verdict_leg.problems}
    assert "LEG_COST_MISMATCH" in codes_leg

    # Tamper total cost
    ans.route.total_cost = 555.55
    verdict_total = verify_answer(ans, state, dataset, settings)
    codes_total = {p.code for p in verdict_total.problems}
    assert "TOTAL_MISMATCH" in codes_total


def test_verifier_detects_floor_change_mismatch(finder, dataset, settings):
    """Problem code FLOOR_CHANGE_MISMATCH when floor_changes differs from legs."""
    ans = run_query(finder, "Café Corner Trail Mix Pouch large")
    assert ans.route is not None

    from planogram_agent.agents.query import ParsedItem, ParsedRequest
    from planogram_agent.agents.routing import plan_trip

    state = RunState(
        session_id="s",
        original_text="Café Corner Trail Mix Pouch large",
        parsed_request=ParsedRequest(
            raw_text="Café Corner Trail Mix Pouch large",
            intent="find",
            items=[ParsedItem(text="Café Corner Trail Mix Pouch large", qty=1)],
        ),
        start="Entrance",
        start_node="L1_ENTRANCE",
    )
    state.routing_result = plan_trip(dataset, start_text="Entrance", skus=["CAF-BUL-014"], settings=settings)

    ans.route.floor_changes = 99  # actual is 1
    verdict = verify_answer(ans, state, dataset, settings)
    codes = {p.code for p in verdict.problems}
    assert "FLOOR_CHANGE_MISMATCH" in codes


def test_verifier_detects_connector_not_allowed(finder, dataset, settings):
    """Problem code CONNECTOR_NOT_ALLOWED when step-free route uses escalator."""
    ans = run_query(finder, "Café Corner Trail Mix Pouch large", accessible_only=False)
    assert ans.route is not None
    # Now mark route as accessible_only=True while it uses escalator
    ans.route.accessible_only = True
    ans.route.connectors_used = [ConnectorType.ESCALATOR]

    state = RunState(session_id="s", original_text="Café Corner Trail Mix Pouch large", accessible_only=True)
    verdict = verify_answer(ans, state, dataset, settings)
    codes = {p.code for p in verdict.problems}
    assert "CONNECTOR_NOT_ALLOWED" in codes


def test_verifier_detects_step_label_unknown(finder, dataset, settings):
    """Problem code STEP_LABEL_UNKNOWN when step has invented label."""
    ans = run_query(finder, "Fresh Farms Red Apples 1 kg")
    assert ans.route is not None
    ans.route.steps[0].from_label = "Narnia Aisle 9"
    state = RunState(session_id="s", original_text="Fresh Farms Red Apples 1 kg")
    verdict = verify_answer(ans, state, dataset, settings)
    codes = {p.code for p in verdict.problems}
    assert "STEP_LABEL_UNKNOWN" in codes


def test_verifier_detects_text_mismatch(finder, dataset, settings):
    """Problem code TEXT_MISMATCH when directions_text contains extra distance or fake place."""
    ans = run_query(finder, "Fresh Farms Red Apples 1 kg")
    assert ans.route is not None
    # Tamper directions_text with extra distance
    ans.route.directions_text += "\n7. Walk 888m to Atlantis."
    state = RunState(session_id="s", original_text="Fresh Farms Red Apples 1 kg")
    verdict = verify_answer(ans, state, dataset, settings)
    codes = {p.code for p in verdict.problems}
    assert "TEXT_MISMATCH" in codes


def test_verifier_detects_status_inconsistent(dataset, settings):
    """Problem code STATUS_INCONSISTENT when answer reports status ok while product is out of stock."""
    ans = Answer(
        status="ok",  # inconsistent: should be partial
        items=[
            ItemResult(
                index=0,
                requested="ArtBox Watercolour Paints 12 pack",
                status="unavailable",
                sku="TOY-ART-005",
                name="ArtBox Watercolour Paints 12 pack",
                quantity=0,
                reason="Out of stock",
            )
        ],
    )
    state = RunState(session_id="s", original_text="ArtBox Watercolour Paints 12 pack")
    verdict = verify_answer(ans, state, dataset, settings)
    codes = {p.code for p in verdict.problems}
    assert "STATUS_INCONSISTENT" in codes


def test_verifier_detects_question_invalid(dataset, settings):
    """Problem code QUESTION_INVALID for question with only 1 option or unknown SKU."""
    # 1. Fewer than 2 options
    ans1 = Answer(
        status="needs_clarification",
        items=[ItemResult(index=0, requested="milk", status="needs_choice")],
        question=Question(
            item_index=0,
            item_text="milk",
            options=[Candidate(sku="DAI-MIL-001", name="Meadow Fresh Whole Milk 1 L", score=1.0)],
        ),
    )
    state = RunState(session_id="s", original_text="milk")
    v1 = verify_answer(ans1, state, dataset, settings)
    assert "QUESTION_INVALID" in {p.code for p in v1.problems}

    # 2. Option SKU not in catalogue
    ans2 = Answer(
        status="needs_clarification",
        items=[ItemResult(index=0, requested="milk", status="needs_choice")],
        question=Question(
            item_index=0,
            item_text="milk",
            options=[
                Candidate(sku="DAI-MIL-001", name="Meadow Fresh Whole Milk 1 L", score=1.0),
                Candidate(sku="BOGUS-SKU-999", name="Fake Milk", score=1.0),
            ],
        ),
    )
    v2 = verify_answer(ans2, state, dataset, settings)
    assert "QUESTION_INVALID" in {p.code for p in v2.problems}


def test_verifier_detects_arrive_step_missing(finder, dataset, settings):
    """ARRIVE_STEP_MISSING problem code when an ordered SKU lacks an arrive step."""
    ans = run_query(finder, "Fresh Farms Red Apples 1 kg")
    assert ans.route is not None
    ans.route.steps = [s for s in ans.route.steps if s.kind != "arrive"]
    state = RunState(session_id="s", original_text="Fresh Farms Red Apples 1 kg")
    verdict = verify_answer(ans, state, dataset, settings)
    assert "ARRIVE_STEP_MISSING" in {p.code for p in verdict.problems}


def test_verifier_detects_arrive_step_duplicate(finder, dataset, settings):
    """ARRIVE_STEP_MISSING problem code when an ordered SKU has duplicate arrive steps."""
    ans = run_query(finder, "Fresh Farms Red Apples 1 kg")
    assert ans.route is not None
    arrive_step = next(s for s in ans.route.steps if s.kind == "arrive")
    ans.route.steps.append(arrive_step.model_copy())
    state = RunState(session_id="s", original_text="Fresh Farms Red Apples 1 kg")
    verdict = verify_answer(ans, state, dataset, settings)
    assert "ARRIVE_STEP_MISSING" in {p.code for p in verdict.problems}


def test_verifier_detects_arrive_step_wrong_product_name(finder, dataset, settings):
    """ARRIVE_STEP_MISSING problem code when arrive step product name does not match catalogue."""
    ans = run_query(finder, "Fresh Farms Red Apples 1 kg")
    assert ans.route is not None
    for s in ans.route.steps:
        if s.kind == "arrive":
            s.product_name = "Completely Invented Apple Name"
    state = RunState(session_id="s", original_text="Fresh Farms Red Apples 1 kg")
    verdict = verify_answer(ans, state, dataset, settings)
    assert "ARRIVE_STEP_MISSING" in {p.code for p in verdict.problems}


def test_verifier_detects_arrive_step_wrong_location_text(finder, dataset, settings):
    """ARRIVE_STEP_MISSING problem code when arrive step place text does not match planogram."""
    ans = run_query(finder, "Fresh Farms Red Apples 1 kg")
    assert ans.route is not None
    for s in ans.route.steps:
        if s.kind == "arrive":
            s.location_text = "Level 99, Outer Space, Bay 42, Shelf 0"
    state = RunState(session_id="s", original_text="Fresh Farms Red Apples 1 kg")
    verdict = verify_answer(ans, state, dataset, settings)
    assert "ARRIVE_STEP_MISSING" in {p.code for p in verdict.problems}


def test_verifier_valid_start_equals_stop_passes(finder, dataset, settings):
    """A valid start-equals-stop route must pass verification without ARRIVE_STEP_MISSING."""
    # Standing at Bakery asking for a bakery product
    ans = run_query(finder, "Daily Bake Plain Bagels 4 pack", start="Bakery")
    assert ans.status == "ok"
    assert ans.verified is True
    assert ans.route is not None
    assert any(s.kind == "arrive" and s.sku == "BAK-BAG-009" for s in ans.route.steps)

    state = RunState(session_id="s", original_text="Daily Bake Plain Bagels 4 pack", start="Bakery")
    verdict = verify_answer(ans, state, dataset, settings)
    assert verdict.ok is True
    assert "ARRIVE_STEP_MISSING" not in {p.code for p in verdict.problems}



def test_repair_path_wrong_once_then_right(dataset, settings):
    """A composer that is wrong once then right gives repaired=True and verified=True."""
    call_count = 0

    def faulty_once_composer(state, ds):
        nonlocal call_count
        call_count += 1
        ans = compose_answer(state, ds)
        if call_count == 1 and ans.items:
            # Inject faulty name on pass 1
            ans.items[0].name = "Corrupted Name That Fails Verification"
        return ans

    orch = Orchestrator(dataset=dataset, settings=settings, composer=faulty_once_composer)
    ans = orch.run("Fresh Farms Red Apples 1 kg")

    assert ans.verified is True
    assert ans.repaired is True
    assert ans.rebuilt is False
    assert ans.items[0].name == "Fresh Farms Red Apples 1 kg"


def test_rebuild_path_composer_always_wrong(dataset, settings):
    """A composer that is always wrong fails repair and gives rebuilt=True and verified=True."""
    def always_wrong_composer(state, ds):
        # Return empty items to trigger persistent failure
        return Answer(status="ok", items=[])

    orch = Orchestrator(dataset=dataset, settings=settings, composer=always_wrong_composer)
    ans = orch.run("Fresh Farms Red Apples 1 kg")

    assert ans.verified is True
    assert ans.rebuilt is True
    assert len(ans.items) == 1
    assert ans.items[0].sku == "PRO-APP-001"
    assert ans.items[0].name == "Fresh Farms Red Apples 1 kg"


def test_rebuild_spy_proves_rebuild_answer_does_not_call_composer(dataset, settings):
    """Spy test proving rebuild_answer independently constructs answer without calling composer."""
    composer_calls = 0

    def spy_composer(state, ds):
        nonlocal composer_calls
        composer_calls += 1
        # Intentionally wrong
        return Answer(status="ok", items=[])

    orch = Orchestrator(dataset=dataset, settings=settings, composer=spy_composer)
    ans = orch.run("Fresh Farms Red Apples 1 kg")

    # Orchestrator called composer in Stage 7 (1 call).
    # Repair failed; Orchestrator triggered REBUILD via rebuild_answer, which must NOT call composer!
    assert composer_calls == 1, f"Expected composer called exactly 1 time, got {composer_calls}"
    assert ans.verified is True
    assert ans.rebuilt is True
    assert len(ans.items) == 1
    assert ans.items[0].sku == "PRO-APP-001"
    assert ans.items[0].name == "Fresh Farms Red Apples 1 kg"


def test_fatal_verification_failure_when_verifier_always_fails(dataset, settings):
    """A verifier that always fails gives status error with 'Could not produce a verified answer'."""
    from planogram_agent.agents.verifier import Problem, Verdict

    def always_fail_verifier(ans, state, ds, sett):
        return Verdict(ok=False, problems=[Problem(code="UNRESOLVABLE_DEFECT", message="Simulated hardware fault")])

    orch = Orchestrator(dataset=dataset, settings=settings, verifier=always_fail_verifier)
    ans = orch.run("Fresh Farms Red Apples 1 kg")

    assert ans.status == "error"
    assert ans.verified is False
    assert ans.messages == ["Could not produce a verified answer"]


def test_verifier_does_not_import_compose_answer_or_composer_status():
    """agents/verifier.py must never import compose_answer or rebuild_answer."""
    source_code = VERIFIER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source_code)

    imported_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.append(alias.name)

    assert "compose_answer" not in imported_names, (
        "agents/verifier.py must NOT import compose_answer"
    )
    assert "rebuild_answer" not in imported_names, (
        "agents/verifier.py must NOT import rebuild_answer"
    )


def test_rebuild_does_not_import_compose_answer():
    """runtime/rebuild.py must never import compose_answer."""
    assert REBUILD_PATH.exists(), f"{REBUILD_PATH} must exist"
    source_code = REBUILD_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source_code)

    imported_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.append(alias.name)

    assert "compose_answer" not in imported_names, (
        "runtime/rebuild.py must NOT import compose_answer"
    )

