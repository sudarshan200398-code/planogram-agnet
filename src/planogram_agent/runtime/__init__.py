"""Runtime orchestration, state management, and consistency checking."""
from .consistency import check_directions_consistency
from .state import Answer, ItemResult, Question, RouteSummary, RunState, TraceEvent


def __getattr__(name: str):
    if name in ("Orchestrator", "SessionStore", "compose_answer"):
        from . import orchestrator

        return getattr(orchestrator, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "Answer",
    "ItemResult",
    "Orchestrator",
    "Question",
    "RouteSummary",
    "RunState",
    "SessionStore",
    "TraceEvent",
    "check_directions_consistency",
    "compose_answer",
]
