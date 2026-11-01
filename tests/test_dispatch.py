"""Agent selection and queue ordering."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.engine.dispatch import (
    AgentCandidate,
    QueueItem,
    blocked_reason,
    explain_no_agent,
    is_runnable,
    order_queue,
    select_agent,
)
from app.models import AgentKind, TaskStatus

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


def _candidate(name, kind, enabled=True, cap=2, active=0):
    return AgentCandidate(
        id=name.lower(),
        name=name,
        kind=kind,
        enabled=enabled,
        max_concurrency=cap,
        active_runs=active,
    )


def test_selects_least_loaded_agent():
    candidates = [
        _candidate("Busy", AgentKind.dispatcher, cap=4, active=3),
        _candidate("Idle", AgentKind.dispatcher, cap=4, active=0),
    ]
    chosen = select_agent(AgentKind.dispatcher, candidates)
    assert chosen is not None
    assert chosen.name == "Idle"


def test_skips_agents_at_capacity():
    candidates = [_candidate("Full", AgentKind.dispatcher, cap=2, active=2)]
    assert select_agent(AgentKind.dispatcher, candidates) is None


def test_skips_disabled_agents():
    candidates = [_candidate("Off", AgentKind.dispatcher, enabled=False)]
    assert select_agent(AgentKind.dispatcher, candidates) is None


def test_ignores_agents_of_other_kinds():
    candidates = [_candidate("Router", AgentKind.route_optimizer)]
    assert select_agent(AgentKind.dispatcher, candidates) is None


def test_tie_breaks_on_name_for_reproducibility():
    candidates = [
        _candidate("Zara", AgentKind.dispatcher),
        _candidate("Adeel", AgentKind.dispatcher),
    ]
    assert select_agent(AgentKind.dispatcher, candidates).name == "Adeel"


def test_explain_no_agent_distinguishes_missing_from_busy():
    missing = explain_no_agent(AgentKind.dispatcher, [])
    assert "No agent registered" in missing

    busy = explain_no_agent(
        AgentKind.dispatcher, [_candidate("Full", AgentKind.dispatcher, cap=1, active=1)]
    )
    assert "at capacity" in busy

    disabled = explain_no_agent(
        AgentKind.dispatcher, [_candidate("Off", AgentKind.dispatcher, enabled=False)]
    )
    assert "disabled" in disabled


def test_queue_orders_by_priority_then_age():
    items = [
        QueueItem("c", 5, NOW, TaskStatus.queued, None, None),
        QueueItem("a", 1, NOW + timedelta(minutes=5), TaskStatus.queued, None, None),
        QueueItem("b", 1, NOW, TaskStatus.queued, None, None),
    ]
    ordered = order_queue(items)
    assert [i.id for i in ordered] == ["b", "a", "c"]


def test_queue_excludes_non_queued_tasks():
    items = [
        QueueItem("done", 1, NOW, TaskStatus.succeeded, None, None),
        QueueItem("waiting", 2, NOW, TaskStatus.queued, None, None),
    ]
    assert [i.id for i in order_queue(items)] == ["waiting"]


def test_dependency_blocks_until_succeeded():
    blocked = QueueItem("t", 1, NOW, TaskStatus.queued, "dep", TaskStatus.running)
    assert is_runnable(blocked) is False

    ready = QueueItem("t", 1, NOW, TaskStatus.queued, "dep", TaskStatus.succeeded)
    assert is_runnable(ready) is True


def test_dependency_failure_blocks_permanently():
    item = QueueItem("t", 1, NOW, TaskStatus.queued, "dep", TaskStatus.failed)
    assert is_runnable(item) is False
    assert "failed" in blocked_reason(item)


def test_blocked_reason_for_missing_dependency():
    item = QueueItem("t", 1, NOW, TaskStatus.queued, "dep", None)
    assert "no longer exists" in blocked_reason(item)


def test_blocked_reason_is_none_when_runnable():
    item = QueueItem("t", 1, NOW, TaskStatus.queued, None, None)
    assert blocked_reason(item) is None
