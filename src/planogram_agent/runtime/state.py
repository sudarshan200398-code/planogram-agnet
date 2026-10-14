"""Runtime state and result schemas for the multi-stage Orchestrator pipeline."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..agents.availability import Availability
from ..agents.query import ParsedRequest
from ..agents.routing import DirectionStep, RoutingResult
from ..agents.search import MatchResult
from ..matching import Candidate
from ..schemas import ConnectorType
from ..tools import Location


class TraceEvent(BaseModel):
    """Execution trace event recorded for an orchestration stage."""

    stage: str
    ok: bool
    ms: float
    note: str = ""


class Question(BaseModel):
    """Clarification question asked to shopper when an item is ambiguous."""

    item_index: int
    item_text: str
    options: list[Candidate] = Field(default_factory=list)


class ItemResult(BaseModel):
    """Comprehensive resolved state for a single requested item."""

    index: int
    requested: str
    qty: int = 1
    status: Literal[
        "available",
        "unavailable",
        "not_found",
        "not_placed",
        "needs_choice",
        "error",
    ]
    sku: str | None = None
    name: str | None = None
    quantity: int = 0
    locations: list[Location] = Field(default_factory=list)
    chosen_location: Location | None = None
    options: list[Candidate] = Field(default_factory=list)
    reason: str | None = None


class RouteSummary(BaseModel):
    """Customer-facing summary of the trip route."""

    start_node: str
    start_label: str
    ordered_skus: list[str]
    total_cost: float
    walking_distance: float
    floor_changes: int
    connectors_used: list[ConnectorType]
    accessible_only: bool
    steps: list[DirectionStep] = Field(default_factory=list)
    directions_text: str = ""


class Answer(BaseModel):
    """Final validated response returned to shopper or interface."""

    status: Literal["ok", "partial", "needs_clarification", "error"]
    items: list[ItemResult] = Field(default_factory=list)
    route: RouteSummary | None = None
    question: Question | None = None
    session_id: str | None = None
    messages: list[str] = Field(default_factory=list)
    verified: bool = False
    repaired: bool = False
    rebuilt: bool = False
    trace: list[TraceEvent] = Field(default_factory=list)


class RunState(BaseModel):
    """Internal mutable state carried through the orchestration pipeline stages."""

    session_id: str
    original_text: str
    start: str | None = None
    floor: int | None = None
    accessible_only: bool = False
    parsed_request: ParsedRequest | None = None
    matches: dict[int, MatchResult] = Field(default_factory=dict)
    availability: dict[int, Availability] = Field(default_factory=dict)
    locations: dict[int, list[Location]] = Field(default_factory=dict)
    routing_result: RoutingResult | None = None
    pending_questions: list[Question] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    trace: list[TraceEvent] = Field(default_factory=list)
    steps_used: int = 0
    started_at: float = 0.0
    start_node: str | None = None
    start_label: str | None = None
