"""Answer-flow state machine (§4.1.1 layer 2) — the only writer of flow status."""

from __future__ import annotations

from enum import StrEnum

from .errors import IllegalFlowTransition


class FlowStatus(StrEnum):
    INIT = "init"
    ASKING = "asking"
    EVALUATING = "evaluating"
    FOLLOW_UP = "follow_up"
    COMPLETED = "completed"


FLOW_TRANSITIONS: dict[FlowStatus, frozenset[FlowStatus]] = {
    FlowStatus.INIT: frozenset({FlowStatus.ASKING, FlowStatus.COMPLETED}),
    FlowStatus.ASKING: frozenset({FlowStatus.EVALUATING, FlowStatus.COMPLETED}),
    FlowStatus.EVALUATING: frozenset(
        {FlowStatus.ASKING, FlowStatus.FOLLOW_UP, FlowStatus.COMPLETED}
    ),
    FlowStatus.FOLLOW_UP: frozenset(
        {FlowStatus.EVALUATING, FlowStatus.ASKING, FlowStatus.COMPLETED}
    ),
    FlowStatus.COMPLETED: frozenset(),
}


def ensure_flow_transition(current: FlowStatus, target: FlowStatus) -> None:
    if current == target:
        return
    if target not in FLOW_TRANSITIONS[current]:
        raise IllegalFlowTransition(f"illegal interview flow transition: {current} -> {target}")
