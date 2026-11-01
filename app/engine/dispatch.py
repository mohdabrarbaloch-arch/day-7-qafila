"""Agent selection and queue ordering.

Two decisions live here, and both are pure functions so they can be tested
without a database:

1. Which agent should take a task (kind match, enabled, under concurrency).
2. In what order should the queue be drained (priority, then age, then DAG).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..models import AgentKind, TaskStatus


@dataclass(frozen=True)
class AgentCandidate:
    id: str
    name: str
    kind: AgentKind
    enabled: bool
    max_concurrency: int
    active_runs: int

    @property
    def has_capacity(self) -> bool:
        return self.enabled and self.active_runs < self.max_concurrency

    @property
    def load_ratio(self) -> float:
        if self.max_concurrency <= 0:
            return 1.0
        return self.active_runs / self.max_concurrency


def select_agent(kind: AgentKind, candidates: list[AgentCandidate]) -> AgentCandidate | None:
    """Pick the least-loaded eligible agent, or None if nobody can take it.

    Ties break on name so the choice is reproducible — a dispatcher debugging
    a run should get the same answer twice.
    """
    eligible = [c for c in candidates if c.kind is kind and c.has_capacity]
    if not eligible:
        return None
    eligible.sort(key=lambda c: (c.load_ratio, c.active_runs, c.name))
    return eligible[0]


def explain_no_agent(kind: AgentKind, candidates: list[AgentCandidate]) -> str:
    """Why did selection fail? Distinguishes 'none registered' from 'all busy'."""
    same_kind = [c for c in candidates if c.kind is kind]
    if not same_kind:
        return f"No agent registered for kind '{kind.value}'."
    disabled = [c.name for c in same_kind if not c.enabled]
    if len(disabled) == len(same_kind):
        return f"All '{kind.value}' agents are disabled: {', '.join(sorted(disabled))}."
    busy = [f"{c.name} ({c.active_runs}/{c.max_concurrency})" for c in same_kind if c.enabled]
    return f"All '{kind.value}' agents are at capacity: {', '.join(sorted(busy))}."


@dataclass(frozen=True)
class QueueItem:
    id: str
    priority: int
    created_at: datetime
    status: TaskStatus
    depends_on_id: str | None
    dependency_status: TaskStatus | None


def is_runnable(item: QueueItem) -> bool:
    """A task runs only when queued and its dependency (if any) succeeded."""
    if item.status is not TaskStatus.queued:
        return False
    if item.depends_on_id is None:
        return True
    return item.dependency_status is TaskStatus.succeeded


def order_queue(items: list[QueueItem]) -> list[QueueItem]:
    """Runnable tasks first, then by priority (1 = highest), then oldest first."""
    runnable = [i for i in items if is_runnable(i)]
    runnable.sort(key=lambda i: (i.priority, i.created_at, i.id))
    return runnable


def blocked_reason(item: QueueItem) -> str | None:
    """Human-readable reason a queued task is not runnable, or None."""
    if item.status is not TaskStatus.queued:
        return f"Task is {item.status.value}, not queued."
    if item.depends_on_id is None:
        return None
    if item.dependency_status is None:
        return "Dependency task no longer exists."
    if item.dependency_status is not TaskStatus.succeeded:
        return f"Dependency is {item.dependency_status.value}, not succeeded."
    return None
