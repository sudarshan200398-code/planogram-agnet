"""Multi-stage deterministic Orchestrator and SessionStore."""
from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Callable

from ..agents.availability import check_availability
from ..agents.query import parse_request
from ..agents.routing import RoutingResult, plan_trip
from ..agents.search import match_item
from ..agents.verifier import compute_expected_status, repair_answer, verify_answer
from ..llm.base import LLMClient
from ..llm.no_model import NoModelClient
from ..settings import Settings, load_settings
from ..tools import Location, get_location, resolve_start
from .rebuild import rebuild_answer
from .state import Answer, ItemResult, Question, RouteSummary, RunState, TraceEvent

if TYPE_CHECKING:
    from ..data_loader import Dataset


class SessionStore:
    """In-memory session store for pending multi-turn user clarification states."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        ttl_seconds: int = 600,
        max_sessions: int = 1000,
    ) -> None:
        self.clock = clock
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._sessions: dict[str, tuple[float, RunState]] = {}

    def _purge(self) -> None:
        """Purge sessions that have exceeded session_ttl_seconds."""
        now = self.clock()
        expired = [
            sid for sid, (created_at, _) in self._sessions.items()
            if now - created_at > self.ttl_seconds
        ]
        for sid in expired:
            self._sessions.pop(sid, None)

    def put(self, state: RunState) -> None:
        """Store a RunState, capping at max_sessions by dropping the oldest."""
        self._purge()
        if len(self._sessions) >= self.max_sessions:
            oldest_sid = min(self._sessions.keys(), key=lambda k: self._sessions[k][0])
            self._sessions.pop(oldest_sid, None)
        self._sessions[state.session_id] = (self.clock(), state)

    def get(self, session_id: str) -> RunState | None:
        """Retrieve a valid, unexpired RunState by session ID."""
        self._purge()
        entry = self._sessions.get(session_id)
        if entry is None:
            return None
        return entry[1]

    def delete(self, session_id: str) -> None:
        """Delete a session by ID."""
        self._sessions.pop(session_id, None)


def _build_route_summary(
    routing_result: RoutingResult,
    dataset: Dataset,
    accessible_only: bool = False,
) -> RouteSummary:
    """Transform a RoutingResult into a customer-facing RouteSummary."""
    node_map = {n.id: n.label for n in dataset.graph.nodes}
    start_label = node_map.get(routing_result.start_node, routing_result.start_node)
    plan = routing_result.trip_plan
    path: list[str] = []
    if plan.legs:
        for leg in plan.legs:
            if not path:
                path.extend(leg.path)
            else:
                path.extend(leg.path[1:])
    elif routing_result.start_node:
        path = [routing_result.start_node]

    return RouteSummary(
        start_node=routing_result.start_node,
        start_label=start_label,
        ordered_skus=plan.ordered_skus,
        total_cost=plan.total_cost,
        walking_distance=plan.walking_distance,
        floor_changes=plan.floor_changes,
        connectors_used=plan.connectors_used,
        accessible_only=accessible_only,
        path=path,
        steps=routing_result.directions,
        directions_text=routing_result.directions_text,
    )


def compose_answer(state: RunState, dataset: Dataset) -> Answer:
    """Build the draft customer Answer from the current RunState."""
    items: list[ItemResult] = []
    prod_by_sku = {p.sku: p for p in dataset.products}
    node_map = {n.id: n.label for n in dataset.graph.nodes}

    # Map leg destination nodes from routing result if available
    sku_to_dest_node: dict[str, str] = {}
    if state.routing_result and state.routing_result.trip_plan.stops:
        for stop_node, stop_skus in state.routing_result.trip_plan.stops:
            for s in stop_skus:
                sku_to_dest_node[s] = stop_node
    elif state.routing_result and state.routing_result.trip_plan.legs:
        # Trace ordered_skus to their matching leg ends
        remaining = list(state.routing_result.trip_plan.ordered_skus)
        for leg in state.routing_result.trip_plan.legs:
            while remaining:
                cand = remaining[0]
                locs = state.locations.get(
                    next(
                        (i for i, it in enumerate(state.parsed_request.items if state.parsed_request else [])
                         if state.matches.get(i) and state.matches[i].chosen and state.matches[i].chosen.sku == cand),
                        -1,
                    ),
                    [],
                )
                if any(l.node_id == leg.end for l in locs):
                    sku_to_dest_node[cand] = leg.end
                    remaining.pop(0)
                else:
                    break

    pending_idx_set = {q.item_index for q in state.pending_questions}

    if state.parsed_request and state.parsed_request.items:
        for idx, req_item in enumerate(state.parsed_request.items):
            match_res = state.matches.get(idx)
            avail = state.availability.get(idx)
            locs = state.locations.get(idx, [])

            if idx in pending_idx_set:
                items.append(
                    ItemResult(
                        index=idx,
                        requested=req_item.text,
                        qty=req_item.qty,
                        status="needs_choice",
                        sku=None,
                        name=None,
                        quantity=0,
                        locations=[],
                        chosen_location=None,
                        options=match_res.options if match_res else [],
                        reason="Item is ambiguous, needs choice",
                    )
                )
            elif match_res is None or match_res.status == "not_found":
                items.append(
                    ItemResult(
                        index=idx,
                        requested=req_item.text,
                        qty=req_item.qty,
                        status="not_found",
                        sku=None,
                        name=None,
                        quantity=0,
                        locations=[],
                        chosen_location=None,
                        options=[],
                        reason="Product not found in catalogue",
                    )
                )
            elif match_res.status == "matched" and match_res.chosen:
                sku = match_res.chosen.sku
                p = prod_by_sku.get(sku)
                p_name = p.name if p else match_res.chosen.name
                qty = avail.quantity if avail else 0

                # Determine chosen location matching planner stop if routed
                chosen_loc: Location | None = None
                chosen_node_id = sku_to_dest_node.get(sku)
                if chosen_node_id:
                    chosen_loc = next((l for l in locs if l.node_id == chosen_node_id), None)
                if chosen_loc is None and locs:
                    chosen_loc = locs[0]

                if avail and avail.status == "unavailable":
                    status = "unavailable"
                    reason = avail.reason or "Out of stock"
                elif not locs:
                    status = "not_placed"
                    reason = "Product has no shelf location in the planogram"
                    chosen_loc = None
                else:
                    status = "available"
                    reason = None

                items.append(
                    ItemResult(
                        index=idx,
                        requested=req_item.text,
                        qty=req_item.qty,
                        status=status,
                        sku=sku,
                        name=p_name,
                        quantity=qty,
                        locations=locs,
                        chosen_location=chosen_loc,
                        options=[],
                        reason=reason,
                    )
                )

    # Build RouteSummary
    route_summary: RouteSummary | None = None
    if state.routing_result and (
        state.routing_result.trip_plan.legs or state.routing_result.trip_plan.ordered_skus
    ):
        route_summary = _build_route_summary(
            state.routing_result,
            dataset,
            accessible_only=state.accessible_only,
        )

    # Pending Question
    question: Question | None = (
        state.pending_questions[0] if state.pending_questions else None
    )

    answer = Answer(
        status="ok",
        items=items,
        route=route_summary,
        question=question,
        session_id=state.session_id,
        messages=list(state.errors),
        verified=False,
        repaired=False,
        rebuilt=False,
        trace=list(state.trace),
    )
    answer.status = compute_expected_status(answer, state)
    return answer


class Orchestrator:
    """Fixed-stage orchestrator managing state, tool invocations, and answer verification."""

    def __init__(
        self,
        dataset: Dataset,
        settings: Settings | None = None,
        client: LLMClient | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        composer: Callable[[RunState, Dataset], Answer] = compose_answer,
        verifier: Callable[[Answer, RunState, Dataset, Settings], object] = verify_answer,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        model_note: str | None = None,
    ) -> None:
        self.dataset = dataset
        self.settings = settings or load_settings()
        self.client = client if client is not None else NoModelClient()
        self.clock = clock
        self.composer = composer
        self.verifier = verifier
        self.id_factory = id_factory
        if model_note is None and isinstance(self.client, NoModelClient):
            model_note = "Using NoModelClient fallback"
        self.model_note = model_note
        self.sessions = SessionStore(
            clock=self.clock,
            ttl_seconds=self.settings.session_ttl_seconds,
            max_sessions=1000,
        )

    @property
    def model_label(self) -> str:
        """User-facing model indicator label."""
        if not isinstance(self.client, NoModelClient):
            model_name = getattr(self.settings, "model_name", "unknown")
            return f"AI model: on ({model_name})"
        return self.model_note or "AI model: off, using simple rules"

    def _execute_stage(
        self,
        state: RunState,
        stage_name: str,
        func: Callable[[], None],
    ) -> bool:
        """Execute an orchestration stage, recording timing and steps toward max_agent_steps."""
        state.steps_used += 1
        t0 = self.clock()
        try:
            func()
            elapsed_ms = round((self.clock() - t0) * 1000.0, 2)
            state.trace.append(TraceEvent(stage=stage_name, ok=True, ms=elapsed_ms))
            return True
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = round((self.clock() - t0) * 1000.0, 2)
            state.trace.append(
                TraceEvent(stage=stage_name, ok=False, ms=elapsed_ms, note=str(exc))
            )
            state.errors.append(f"{stage_name} error: {exc}")
            return False

    def _has_exceeded_limits(self, state: RunState) -> bool:
        """Check wall-clock deadline and max_agent_steps limits."""
        if state.steps_used >= self.settings.max_agent_steps:
            return True
        if self.clock() - state.started_at > self.settings.max_seconds:
            return True
        return False

    def _run_from_stage(self, state: RunState, from_stage: str = "PARSE") -> Answer:
        """Run orchestration pipeline starting from a specified stage."""
        dataset = self.dataset
        settings = self.settings

        # Stage 1: PARSE
        if from_stage == "PARSE":
            def _parse_stage() -> None:
                parsed = parse_request(
                    state.original_text,
                    client=self.client,
                    settings=settings,
                    dataset=dataset,
                    clock=self.clock,
                )
                if state.start is not None:
                    parsed.start = state.start
                else:
                    state.start = parsed.start
                if state.accessible_only:
                    parsed.accessible_only = state.accessible_only
                else:
                    state.accessible_only = parsed.accessible_only
                state.parsed_request = parsed

            self._execute_stage(state, "PARSE", _parse_stage)

            if state.parsed_request is None or state.parsed_request.intent == "unknown" or not state.parsed_request.items:
                reason = (
                    state.parsed_request.reason
                    if state.parsed_request and state.parsed_request.reason
                    else "Input could not be recognized as a valid product request"
                )
                state.errors.append(reason)
                draft = self.composer(state, dataset)
                draft.status = "error"
                return draft

        if self._has_exceeded_limits(state):
            draft = self.composer(state, dataset)
            draft.messages.append("Execution limit reached before matching")
            draft.status = "partial" if draft.items else "error"
            return draft

        # Stage 2: MATCH
        if from_stage in ("PARSE", "MATCH"):
            def _match_stage() -> None:
                for idx, it in enumerate(state.parsed_request.items if state.parsed_request else []):
                    try:
                        res = match_item(it.text, dataset, settings)
                        state.matches[idx] = res
                    except Exception as e:  # noqa: BLE001
                        state.errors.append(f"Matching failed for item '{it.text}': {e}")

            self._execute_stage(state, "MATCH", _match_stage)

        if self._has_exceeded_limits(state):
            draft = self.composer(state, dataset)
            draft.messages.append("Execution limit reached during matching")
            draft.status = "partial"
            return draft

        # Stage 3: CLARIFY
        if from_stage in ("PARSE", "MATCH", "CLARIFY"):
            def _clarify_stage() -> None:
                state.pending_questions = []
                for idx, it in enumerate(state.parsed_request.items if state.parsed_request else []):
                    m = state.matches.get(idx)
                    if m and m.status == "ambiguous":
                        state.pending_questions.append(
                            Question(
                                item_index=idx,
                                item_text=it.text,
                                options=m.options,
                            )
                        )

            self._execute_stage(state, "CLARIFY", _clarify_stage)

        if self._has_exceeded_limits(state):
            draft = self.composer(state, dataset)
            draft.status = "partial"
            return draft

        # Stage 4: AVAILABILITY
        if from_stage in ("PARSE", "MATCH", "CLARIFY", "AVAILABILITY"):
            def _avail_stage() -> None:
                for idx, m in state.matches.items():
                    if m.status == "matched" and m.chosen:
                        try:
                            state.availability[idx] = check_availability(
                                m.chosen.sku, dataset
                            )
                        except Exception as e:  # noqa: BLE001
                            state.errors.append(f"Availability check failed for {m.chosen.sku}: {e}")

            self._execute_stage(state, "AVAILABILITY", _avail_stage)

        if self._has_exceeded_limits(state):
            draft = self.composer(state, dataset)
            draft.status = "partial"
            return draft

        # Stage 5: LOCATE
        if from_stage in ("PARSE", "MATCH", "CLARIFY", "AVAILABILITY", "LOCATE"):
            def _locate_stage() -> None:
                for idx, m in state.matches.items():
                    if m.status == "matched" and m.chosen:
                        try:
                            state.locations[idx] = get_location(
                                m.chosen.sku, dataset
                            )
                        except Exception as e:  # noqa: BLE001
                            state.errors.append(f"Locating failed for {m.chosen.sku}: {e}")

            self._execute_stage(state, "LOCATE", _locate_stage)

        if self._has_exceeded_limits(state):
            draft = self.composer(state, dataset)
            draft.status = "partial"
            return draft

        # If any item is ambiguous, do NOT route, store RunState in SessionStore and return needs_clarification
        if state.pending_questions:
            self.sessions.put(state)
            draft = self.composer(state, dataset)
            draft.status = "needs_clarification"
            return draft

        # Stage 6: ROUTE
        def _route_stage() -> None:
            routable_skus: list[str] = []
            for idx, m in state.matches.items():
                if m.status == "matched" and m.chosen:
                    sku = m.chosen.sku
                    av = state.availability.get(idx)
                    locs = state.locations.get(idx, [])
                    if av and av.status == "available" and locs:
                        routable_skus.append(sku)

            if not routable_skus:
                state.routing_result = None
                return

            try:
                start_node = resolve_start(state.start, dataset, floor=state.floor)
                state.start_node = start_node
            except ValueError as ve:
                state.errors.append(str(ve))
                state.routing_result = None
                return

            try:
                r_res = plan_trip(
                    dataset,
                    start_text=state.start,
                    floor=state.floor,
                    skus=routable_skus,
                    accessible_only=state.accessible_only,
                    settings=settings,
                )
                state.routing_result = r_res
            except Exception as e:  # noqa: BLE001
                state.errors.append(f"Routing failed: {e}")
                state.routing_result = None

        self._execute_stage(state, "ROUTE", _route_stage)

        if self._has_exceeded_limits(state):
            draft = self.composer(state, dataset)
            draft.status = "partial"
            return draft

        # Stage 7: COMPOSE
        t0 = self.clock()
        draft_answer = self.composer(state, dataset)
        elapsed_ms = round((self.clock() - t0) * 1000.0, 2)
        state.trace.append(
            TraceEvent(
                stage="COMPOSE",
                ok=True,
                ms=elapsed_ms,
                note=f"Items: {len(draft_answer.items)}",
            )
        )
        draft_answer.trace = list(state.trace)

        # Stage 8: VERIFY & REPAIR Loop
        t0 = self.clock()
        verdict = self.verifier(draft_answer, state, dataset, settings)
        elapsed_ms = round((self.clock() - t0) * 1000.0, 2)
        v_note = f"Problems: {len(verdict.problems)}" if not verdict.ok else "Audit passed"
        state.trace.append(
            TraceEvent(
                stage="VERIFY",
                ok=verdict.ok,
                ms=elapsed_ms,
                note=v_note,
            )
        )
        draft_answer.trace = list(state.trace)

        if verdict.ok:
            draft_answer.verified = True
            return draft_answer

        # Verification loop with repairs
        for rep_idx in range(settings.max_repairs):
            t0 = self.clock()
            draft_answer = repair_answer(draft_answer, verdict, state, dataset, settings)
            elapsed_ms = round((self.clock() - t0) * 1000.0, 2)
            draft_answer.repaired = True
            state.trace.append(
                TraceEvent(
                    stage="REPAIR",
                    ok=True,
                    ms=elapsed_ms,
                    note=f"Repair pass {rep_idx + 1}",
                )
            )
            draft_answer.trace = list(state.trace)

            t0 = self.clock()
            verdict = self.verifier(draft_answer, state, dataset, settings)
            elapsed_ms = round((self.clock() - t0) * 1000.0, 2)
            v_note = (
                f"Problems after repair: {len(verdict.problems)}"
                if not verdict.ok
                else "Audit passed after repair"
            )
            state.trace.append(
                TraceEvent(
                    stage="VERIFY",
                    ok=verdict.ok,
                    ms=elapsed_ms,
                    note=v_note,
                )
            )
            draft_answer.trace = list(state.trace)
            if verdict.ok:
                draft_answer.verified = True
                return draft_answer

        # Rebuild answer if repairs failed
        t0 = self.clock()
        rebuilt = rebuild_answer(state, dataset, settings)
        elapsed_ms = round((self.clock() - t0) * 1000.0, 2)
        rebuilt.rebuilt = True
        state.trace.append(
            TraceEvent(
                stage="REBUILD",
                ok=True,
                ms=elapsed_ms,
                note="Rebuilt deterministically from facts",
            )
        )
        rebuilt.trace = list(state.trace)

        t0 = self.clock()
        verdict = self.verifier(rebuilt, state, dataset, settings)
        elapsed_ms = round((self.clock() - t0) * 1000.0, 2)
        v_note = (
            f"Problems after rebuild: {len(verdict.problems)}"
            if not verdict.ok
            else "Audit passed after rebuild"
        )
        state.trace.append(
            TraceEvent(
                stage="VERIFY",
                ok=verdict.ok,
                ms=elapsed_ms,
                note=v_note,
            )
        )
        rebuilt.trace = list(state.trace)

        if verdict.ok:
            rebuilt.verified = True
            return rebuilt

        # Fatal verification failure
        return Answer(
            status="error",
            items=draft_answer.items,
            messages=["Could not produce a verified answer"],
            verified=False,
            repaired=draft_answer.repaired,
            rebuilt=True,
            trace=list(state.trace),
        )

    def run(
        self,
        text: str,
        *,
        start: str | None = None,
        floor: int | None = None,
        accessible_only: bool | None = None,
    ) -> Answer:
        """Run a shopper query through the multi-stage pipeline."""
        session_id = self.id_factory()
        state = RunState(
            session_id=session_id,
            original_text=text,
            start=start,
            floor=floor,
            accessible_only=accessible_only or False,
            started_at=self.clock(),
        )

        if self.model_note:
            state.trace.append(
                TraceEvent(stage="MODEL_NOTE", ok=True, ms=0.0, note=self.model_note)
            )

        return self._run_from_stage(state, from_stage="PARSE")


    def answer_question(
        self,
        session_id: str,
        item_index: int,
        sku: str,
    ) -> Answer:
        """Resolve a clarification question with shopper's SKU choice and resume execution."""
        state = self.sessions.get(session_id)
        if state is None:
            return Answer(
                status="error",
                messages=["This question has expired, please ask again"],
            )

        # Find question matching item_index
        q_idx = next(
            (i for i, q in enumerate(state.pending_questions) if q.item_index == item_index),
            None,
        )
        if q_idx is None:
            return Answer(
                status="error",
                messages=[f"No pending question found for item index {item_index}"],
            )

        question = state.pending_questions[q_idx]
        chosen_opt = next((o for o in question.options if o.sku == sku), None)
        if chosen_opt is None:
            # SKU is not one of offered options: keep question pending with message
            draft = self.composer(state, self.dataset)
            draft.messages.append(
                f"Selected SKU '{sku}' is not one of the offered options. "
                f"Please select from: {', '.join(o.sku for o in question.options)}"
            )
            draft.status = "needs_clarification"
            return draft

        # Valid choice resolves that item
        from ..agents.search import MatchResult
        state.matches[item_index] = MatchResult(
            status="matched",
            chosen=chosen_opt,
            options=[],
        )
        state.pending_questions.pop(q_idx)

        # If more items remain unresolved, ask the next
        if state.pending_questions:
            self.sessions.put(state)
            draft = self.composer(state, self.dataset)
            draft.status = "needs_clarification"
            return draft

        # Otherwise continue from AVAILABILITY
        self.sessions.delete(session_id)
        return self._run_from_stage(state, from_stage="AVAILABILITY")
