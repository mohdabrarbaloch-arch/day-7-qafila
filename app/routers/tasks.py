"""Task queue, dispatch, and run inspection."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_role
from ..engine import dispatch, executor
from ..models import (
    Agent,
    AuditEvent,
    Role,
    Run,
    RunStatus,
    Shipment,
    Task,
    TaskStatus,
    User,
)
from ..schemas import DispatchResult, RunOut, TaskCreate, TaskOut

router = APIRouter(prefix="/api", tags=["tasks"])


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    task_status: TaskStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Task]:
    stmt = select(Task).order_by(Task.created_at.desc()).limit(limit)
    if task_status is not None:
        stmt = stmt.where(Task.status == task_status)
    return list(db.scalars(stmt))


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.operator)),
) -> Task:
    if payload.shipment_id is not None and db.get(Shipment, payload.shipment_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Shipment '{payload.shipment_id}' does not exist.",
        )
    if payload.depends_on_id is not None:
        dependency = db.get(Task, payload.depends_on_id)
        if dependency is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Dependency task '{payload.depends_on_id}' does not exist.",
            )
        if dependency.id == payload.depends_on_id and dependency.status is TaskStatus.succeeded:
            pass  # a completed dependency is a valid starting point

    task = Task(
        title=payload.title,
        kind=payload.kind,
        priority=payload.priority,
        payload=payload.payload,
        shipment_id=payload.shipment_id,
        depends_on_id=payload.depends_on_id,
        owner_id=user.id,
    )
    db.add(task)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="task.created",
            entity_type="task",
            entity_id=task.id,
            detail={"kind": task.kind.value, "priority": task.priority},
        )
    )
    db.commit()
    db.refresh(task)
    return task


@router.post("/tasks/dispatch", response_model=DispatchResult)
def dispatch_tasks(
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.operator)),
    max_tasks: int = Query(default=10, ge=1, le=50),
) -> DispatchResult:
    """Drain the runnable queue, respecting dependencies and agent capacity."""
    queued = list(db.scalars(select(Task).where(Task.status == TaskStatus.queued)))

    # Build the queue view with each task's dependency status resolved.
    items: list[dispatch.QueueItem] = []
    for task in queued:
        dep_status = None
        if task.depends_on_id:
            dep = db.get(Task, task.depends_on_id)
            dep_status = dep.status if dep else None
        items.append(
            dispatch.QueueItem(
                id=task.id,
                priority=task.priority,
                created_at=task.created_at,
                status=task.status,
                depends_on_id=task.depends_on_id,
                dependency_status=dep_status,
            )
        )

    ordered = dispatch.order_queue(items)[:max_tasks]

    agents = list(db.scalars(select(Agent)))
    active_counts = dict(
        db.execute(
            select(Run.agent_id, func.count(Run.id))
            .where(Run.status == RunStatus.running)
            .group_by(Run.agent_id)
        ).all()
    )
    candidates = [
        dispatch.AgentCandidate(
            id=a.id,
            name=a.name,
            kind=a.kind,
            enabled=a.enabled,
            max_concurrency=a.max_concurrency,
            active_runs=int(active_counts.get(a.id, 0)),
        )
        for a in agents
    ]

    dispatched: list[Run] = []
    skipped: list[dict[str, str]] = []

    for item in ordered:
        task = db.get(Task, item.id)
        if task is None:
            continue
        chosen = dispatch.select_agent(task.kind, candidates)
        if chosen is None:
            skipped.append(
                {"task_id": task.id, "reason": dispatch.explain_no_agent(task.kind, candidates)}
            )
            continue

        agent = db.get(Agent, chosen.id)
        if agent is None:
            skipped.append({"task_id": task.id, "reason": "Agent vanished mid-dispatch."})
            continue

        run = executor.execute_task(db, task, agent)
        dispatched.append(run)

        # Reflect the new load so a second task in this same batch sees it.
        for index, candidate in enumerate(candidates):
            if candidate.id == chosen.id:
                candidates[index] = dispatch.AgentCandidate(
                    id=candidate.id,
                    name=candidate.name,
                    kind=candidate.kind,
                    enabled=candidate.enabled,
                    max_concurrency=candidate.max_concurrency,
                    active_runs=candidate.active_runs + 1,
                )

    # Anything queued but not runnable gets an explicit reason, not silence.
    dispatched_ids = {r.task_id for r in dispatched}
    skipped_ids = {s["task_id"] for s in skipped}
    for item in items:
        if item.id in dispatched_ids or item.id in skipped_ids:
            continue
        reason = dispatch.blocked_reason(item)
        if reason:
            skipped.append({"task_id": item.id, "reason": reason})

    db.add(
        AuditEvent(
            actor_id=user.id,
            action="tasks.dispatched",
            entity_type="task",
            entity_id="batch",
            detail={"dispatched": len(dispatched), "skipped": len(skipped)},
        )
    )
    db.commit()

    for run in dispatched:
        db.refresh(run)

    message = (
        f"Dispatched {len(dispatched)} task(s); {len(skipped)} left in the queue."
        if dispatched
        else f"Nothing dispatched. {len(skipped)} task(s) waiting."
    )
    return DispatchResult(
        dispatched=[RunOut.model_validate(r) for r in dispatched],
        skipped=skipped,
        message=message,
    )


@router.get("/tasks/{task_id}/runs", response_model=list[RunOut])
def task_runs(
    task_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[Run]:
    if db.get(Task, task_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return list(
        db.scalars(select(Run).where(Run.task_id == task_id).order_by(Run.started_at.desc()))
    )


@router.get("/runs", response_model=list[RunOut])
def list_runs(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Run]:
    return list(db.scalars(select(Run).order_by(Run.started_at.desc()).limit(limit)))
