"""Edge-case test matrix running end to end through Orchestrator and AppTest."""
from __future__ import annotations

import json
from pathlib import Path
from typing import get_args
import pytest

from streamlit.testing.v1 import AppTest

from planogram_agent.agents.verifier import verify_answer
from planogram_agent.data_loader import load_dataset
from planogram_agent.interface import answer_question, create_finder, run_query
from planogram_agent.llm.base import LLMClient
from planogram_agent.llm.no_model import ModelUnavailableError, NoModelClient
import planogram_agent.schemas as schemas
from planogram_agent.runtime.orchestrator import Orchestrator
from planogram_agent.runtime.state import Answer, ItemResult, RunState
from planogram_agent.settings import Settings

STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "store_demo"
EDGE_CASES_PATH = Path(__file__).resolve().parent / "edge_cases.json"
APP_FILE = str(Path(__file__).resolve().parent.parent / "src" / "planogram_agent" / "ui" / "streamlit_app.py")

# Dynamically discover allowed status values from schemas or state
if hasattr(schemas, "ResponseStatus"):
    ALLOWED_STATUSES = set(get_args(schemas.ResponseStatus))
elif hasattr(schemas, "AnswerStatus"):
    ALLOWED_STATUSES = set(get_args(schemas.AnswerStatus))
else:
    ALLOWED_STATUSES = set(get_args(Answer.model_fields["status"].annotation))


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(STORE_DIR, validate=True)


@pytest.fixture(scope="module")
def settings():
    return Settings()


@pytest.fixture(scope="module")
def finder(dataset, settings):
    return create_finder(STORE_DIR, settings=settings, client=NoModelClient())


def load_all_cases() -> list[dict]:
    with open(EDGE_CASES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


ALL_CASES = load_all_cases()
CASE_MAP = {c["id"]: c for c in ALL_CASES}


def _verify_common_invariants(ans: Answer, dataset: object, settings: object):
    assert ans.status in ALLOWED_STATUSES, f"Status '{ans.status}' not in allowed {ALLOWED_STATUSES}"
    valid_skus = {p.sku for p in dataset.products}
    for it in ans.items:
        if it.sku is not None:
            assert it.sku in valid_skus, f"SKU '{it.sku}' not found in dataset products"
    if ans.verified:
        dummy_state = RunState(session_id=ans.session_id or "test", original_text="test")
        verdict = verify_answer(ans, dummy_state, dataset, settings)
        assert verdict.ok, f"Answer marked verified=True failed verify_answer: {verdict.problems}"


def get_parametrized_cases():
    return [
        pytest.param(c, id=c["id"])
        for c in ALL_CASES
        if c["group"] not in ("session", "failure injection", "UI")
    ]


@pytest.mark.parametrize("case", get_parametrized_cases())
def test_standard_edge_cases(finder, dataset, settings, case):
    """Run standard input, hostile, quantities, matching, availability, location edge cases."""
    cid = case["id"]
    query = case["input_text"]
    start = case.get("start")
    floor = case.get("floor")
    accessible_only = case.get("accessible_only", False)
    exp = case["expected"]

    # Execute
    ans = run_query(
        finder,
        query,
        start=start,
        floor=floor,
        accessible_only=accessible_only,
    )

    # Invariants
    _verify_common_invariants(ans, dataset, settings)

    # Status check
    assert ans.status == exp["response_status"], (
        f"[{cid}] Expected status '{exp['response_status']}', got '{ans.status}'. Messages: {ans.messages}"
    )

    # Item statuses check
    if "item_statuses" in exp:
        exp_item_statuses = exp["item_statuses"]
        act_item_statuses = [it.status for it in ans.items]
        assert act_item_statuses == exp_item_statuses, (
            f"[{cid}] Expected item statuses {exp_item_statuses}, got {act_item_statuses}"
        )

    # Route check
    if "route_exists" in exp:
        has_route = ans.route is not None
        assert has_route == exp["route_exists"], (
            f"[{cid}] Expected route_exists={exp['route_exists']}, got {has_route}"
        )

    # Truncation message check for QTY-01
    if cid == "QTY-01":
        assert any("truncated" in m.lower() for m in ans.messages), (
            f"[{cid}] Expected truncation message in messages: {ans.messages}"
        )


def test_session_unoffered_sku(finder, dataset, settings):
    """SES-01: Answering with an SKU that was not offered."""
    case = CASE_MAP["SES-01"]
    exp = case["expected"]
    ans = run_query(finder, case["input_text"])
    assert ans.status == "needs_clarification", f"[SES-01] Expected initial needs_clarification, got {ans.status}"
    assert ans.question is not None

    q = ans.question
    bad_sku = "NONEXISTENT-SKU-999"
    ans2 = answer_question(finder, ans.session_id, q.item_index, bad_sku)

    _verify_common_invariants(ans2, dataset, settings)
    assert ans2.status == exp["response_status"], (
        f"[SES-01] Expected status '{exp['response_status']}', got '{ans2.status}'"
    )
    assert any("not one of the offered options" in m for m in ans2.messages), (
        f"[SES-01] Expected rejected option message, got {ans2.messages}"
    )


def test_session_answer_twice(finder, dataset, settings):
    """SES-02: Answering twice."""
    case = CASE_MAP["SES-02"]
    exp = case["expected"]
    ans = run_query(finder, case["input_text"])
    assert ans.status == "needs_clarification"
    assert ans.question is not None

    q = ans.question
    opt_sku = q.options[0].sku
    ans2 = answer_question(finder, ans.session_id, q.item_index, opt_sku)
    assert ans2.status in ("ok", "partial")

    # Second answer on the same session
    ans3 = answer_question(finder, ans.session_id, q.item_index, opt_sku)
    _verify_common_invariants(ans3, dataset, settings)
    assert ans3.status == exp["response_status"], (
        f"[SES-02] Expected status '{exp['response_status']}', got '{ans3.status}'"
    )
    assert any("expired" in m.lower() for m in ans3.messages), (
        f"[SES-02] Expected expired message, got {ans3.messages}"
    )


def test_session_answer_after_expiry(dataset, settings):
    """SES-03: Answering after session expiry."""
    case = CASE_MAP["SES-03"]
    exp = case["expected"]
    fake_time = [1000.0]

    def mock_clock() -> float:
        return fake_time[0]

    f = Orchestrator(dataset=dataset, settings=settings, client=NoModelClient(), clock=mock_clock)
    ans = f.run(case["input_text"])
    assert ans.status == "needs_clarification"
    assert ans.question is not None

    q = ans.question
    opt_sku = q.options[0].sku

    # Advance time past TTL (default 600s)
    fake_time[0] += 700.0

    ans2 = f.answer_question(ans.session_id, q.item_index, opt_sku)
    _verify_common_invariants(ans2, dataset, settings)
    assert ans2.status == exp["response_status"], (
        f"[SES-03] Expected status '{exp['response_status']}', got '{ans2.status}'"
    )
    assert any("expired" in m.lower() for m in ans2.messages), (
        f"[SES-03] Expected expiry message, got {ans2.messages}"
    )


def test_session_new_request_while_pending(finder, dataset, settings):
    """SES-04: New request while a question is pending."""
    case = CASE_MAP["SES-04"]
    exp = case["expected"]

    # First request creates pending session
    ans1 = run_query(finder, case["input_text"])
    assert ans1.status == "needs_clarification"
    assert ans1.question is not None

    # New request executes cleanly
    ans2 = run_query(finder, case["second_query"])
    _verify_common_invariants(ans2, dataset, settings)
    assert ans2.status == exp["response_status"], (
        f"[SES-04] Expected status '{exp['response_status']}', got '{ans2.status}'"
    )
    assert (ans2.route is not None) == exp["route_exists"]


def test_failure_injection_composer_wrong_once(dataset, settings):
    """FLI-01: Composer returns wrong answer once, repaired by Verifier."""
    case = CASE_MAP["FLI-01"]
    from planogram_agent.runtime.orchestrator import compose_answer

    call_count = [0]

    def faulty_composer(state: RunState, ds: object) -> Answer:
        draft = compose_answer(state, ds)
        if call_count[0] == 0:
            call_count[0] += 1
            # Corrupt the answer: wrong quantity
            if draft.items:
                draft.items[0].quantity = 9999
        return draft

    f = Orchestrator(
        dataset=dataset,
        settings=settings,
        client=NoModelClient(),
        composer=faulty_composer,
    )
    ans = f.run(case["input_text"])
    _verify_common_invariants(ans, dataset, settings)
    assert ans.status == case["expected"]["response_status"], (
        f"[FLI-01] Expected status '{case['expected']['response_status']}', got '{ans.status}'"
    )
    assert ans.repaired is True, f"[FLI-01] Expected repaired=True, got {ans.repaired}"
    assert ans.verified is True, f"[FLI-01] Expected verified=True, got {ans.verified}"


def test_failure_injection_composer_always_wrong(dataset, settings):
    """FLI-02: Composer always wrong, recovered via rebuild."""
    case = CASE_MAP["FLI-02"]
    from planogram_agent.runtime.orchestrator import compose_answer

    def always_faulty_composer(state: RunState, ds: object) -> Answer:
        draft = compose_answer(state, ds)
        # Corrupt the SKU on every pass so repair cannot guess the true SKU
        if draft.items:
            draft.items[0].sku = "UNKNOWN_INVENTED_SKU_999"
        return draft

    f = Orchestrator(
        dataset=dataset,
        settings=settings,
        client=NoModelClient(),
        composer=always_faulty_composer,
    )
    ans = f.run(case["input_text"])
    _verify_common_invariants(ans, dataset, settings)
    assert ans.status == case["expected"]["response_status"], (
        f"[FLI-02] Expected status '{case['expected']['response_status']}', got '{ans.status}'"
    )
    assert ans.rebuilt is True, f"[FLI-02] Expected rebuilt=True, got {ans.rebuilt}"
    assert ans.verified is True, f"[FLI-02] Expected verified=True, got {ans.verified}"


def test_failure_injection_tool_raises_for_sku(finder, dataset, settings, monkeypatch):
    """FLI-03: Tool raises for one SKU, handled safely."""
    case = CASE_MAP["FLI-03"]
    import planogram_agent.runtime.orchestrator as orch_mod

    def faulty_avail(sku, ds):
        raise RuntimeError("Hardware inventory database connection timeout")

    monkeypatch.setattr(orch_mod, "check_availability", faulty_avail)

    ans = run_query(finder, case["input_text"])
    _verify_common_invariants(ans, dataset, settings)
    assert ans.status in ("partial", "error"), (
        f"[FLI-03] Expected safe status 'partial' or 'error', got '{ans.status}'"
    )
    assert any("failed" in m.lower() or "error" in m.lower() for m in ans.messages or []), (
        f"[FLI-03] Expected failure/error message recorded in answer: {ans.messages}"
    )


def test_failure_injection_model_unavailable(dataset, settings):
    """FLI-04: Client raises ModelUnavailableError, fallback handles query."""
    case = CASE_MAP["FLI-04"]

    class FailingClient(LLMClient):
        def generate(self, system: str, user: str, timeout: float = 5.0) -> str:
            raise ModelUnavailableError("Simulated API 503 service unavailable")

    f = Orchestrator(
        dataset=dataset,
        settings=settings,
        client=FailingClient(),
    )
    ans = f.run(case["input_text"])
    _verify_common_invariants(ans, dataset, settings)
    assert ans.status == case["expected"]["response_status"], (
        f"[FLI-04] Expected status '{case['expected']['response_status']}', got '{ans.status}'"
    )
    assert (ans.route is not None) == case["expected"]["route_exists"]


def test_ui_empty_text():
    """UI-01: Empty text shows info message without crash."""
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.text_area[0].input("   ")
    at.button[3].click().run()

    assert not at.exception, "[UI-01] Unexpected exception in Streamlit AppTest"
    assert len(at.info) >= 1, "[UI-01] Expected info message for empty input"
    assert at.session_state.last_answer is None, "[UI-01] Expected last_answer to be None"


def test_ui_600_characters():
    """UI-02: 600 characters safely rejected with error."""
    case = CASE_MAP["UI-02"]
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.text_area[0].input(case["input_text"])
    at.button[3].click().run()

    assert not at.exception, "[UI-02] Unexpected exception in Streamlit AppTest"
    ans = at.session_state.last_answer
    assert ans is not None, "[UI-02] Expected answer generated"
    assert ans.status == "error", f"[UI-02] Expected status 'error', got '{ans.status}'"


def test_ui_hostile_text():
    """UI-03: Hostile script text handled safely."""
    case = CASE_MAP["UI-03"]
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.text_area[0].input(case["input_text"])
    at.button[3].click().run()

    assert not at.exception, "[UI-03] Unexpected exception in Streamlit AppTest"
    ans = at.session_state.last_answer
    assert ans is not None, "[UI-03] Expected answer generated"
    assert ans.status in ("partial", "error"), f"[UI-03] Expected status partial or error, got '{ans.status}'"


def test_ui_rapid_second_click():
    """UI-04: Rapid second click on Find executes cleanly."""
    case = CASE_MAP["UI-04"]
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.text_area[0].input(case["input_text"])
    at.button[3].click().run()
    at.button[3].click().run()

    assert not at.exception, "[UI-04] Unexpected exception on second click"
    ans = at.session_state.last_answer
    assert ans is not None, "[UI-04] Expected answer generated"
    assert ans.status == "ok", f"[UI-04] Expected status 'ok', got '{ans.status}'"


def test_ui_change_start_after_answer():
    """UI-05: Changing start point after an answer updates route."""
    case = CASE_MAP["UI-05"]
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.text_area[0].input(case["input_text"])
    at.button[3].click().run()

    assert not at.exception, "[UI-05] Exception on first run"
    ans1 = at.session_state.last_answer
    assert ans1.route is not None
    assert ans1.route.start_label == "Entrance"

    # Change start point to Produce and re-run
    at.sidebar.selectbox[0].select("Produce")
    at.button[3].click().run()

    assert not at.exception, "[UI-05] Exception after changing start point"
    ans2 = at.session_state.last_answer
    assert ans2.route is not None
    assert ans2.route.start_label == "Produce"


def test_ui_step_free_level_1():
    """UI-06: Step-free toggle on Level 1-only request."""
    case = CASE_MAP["UI-06"]
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.sidebar.toggle[0].set_value(True)
    at.text_area[0].input(case["input_text"])
    at.button[3].click().run()

    assert not at.exception, "[UI-06] Exception on step-free request"
    ans = at.session_state.last_answer
    assert ans is not None
    assert ans.status == "ok"
    assert ans.route is not None
    assert ans.route.accessible_only is True
    assert ans.route.floor_changes == 0


def test_unit_plain_newline_separated_list(finder):
    """Unit test: plain newline list and casual greeting message with newlines."""
    # Plain newline list gives 2 items
    query1 = "Daily Bake Plain Bagels 4 pack\nDaily Bake White Sandwich Bread 400 g"
    ans1 = run_query(finder, query1)
    assert ans1.status == "ok"
    assert len(ans1.items) == 2
    assert ans1.items[0].name == "Daily Bake Plain Bagels 4 pack"
    assert ans1.items[1].name == "Daily Bake White Sandwich Bread 400 g"

    # Casual multiline message: 'hi\nI need milk\nand bread' drops greeting and gives 2 items
    query2 = "hi\nI need milk\nand bread"
    ans2 = run_query(finder, query2)
    assert ans2.status == "needs_clarification"
    assert len(ans2.items) == 2
    assert ans2.items[0].requested.lower() == "milk"
    assert ans2.items[1].requested.lower() == "bread"


def test_unit_zero_and_negative_quantity_clamping(finder):
    """Unit test: quantity <= 0 is clamped to 1 without raw validation errors."""
    query = "0 Daily Bake Plain Bagels 4 pack and -5 Daily Bake White Sandwich Bread 400 g"
    ans = run_query(finder, query)
    assert ans.status == "ok"
    assert len(ans.items) == 2
    assert ans.items[0].qty == 1
    assert ans.items[1].qty == 1
    assert not any("validation error" in m.lower() for m in ans.messages)


def test_unit_resolve_start_single_floor_mismatch(finder, dataset):
    """Unit test: single-floor start landmark mismatch raises error and reports plain message."""
    from planogram_agent.tools import resolve_start

    with pytest.raises(ValueError, match="Start point 'Bakery' not found on Level 2"):
        resolve_start("Bakery", dataset, floor=2)

    ans = run_query(finder, "Daily Bake Plain Bagels 4 pack", start="Bakery", floor=2)
    assert ans.status == "partial"
    assert ans.route is None
    assert any("Start point 'Bakery' not found on Level 2" in m for m in ans.messages)
    assert not any("traceback" in m.lower() for m in ans.messages)


def test_unit_ui_start_on_level_2_default_floor():
    """Unit test: UI with default sidebar ('Use my message, or the entrance') picks Level 2 Café from message."""
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    assert at.sidebar.selectbox[0].value == "Use my message, or the entrance"

    query = "CleanHome Trash Bags 20 pack, I'm near the Café"
    at.text_area[0].input(query)
    at.button[3].click().run()

    assert not at.exception
    ans = at.session_state.last_answer
    assert ans is not None
    assert ans.status == "ok"
    assert ans.route is not None
    assert "Caf" in ans.route.start_label
    assert ans.route.floor_changes == 0

