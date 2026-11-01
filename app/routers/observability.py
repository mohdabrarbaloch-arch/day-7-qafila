"""Metrics and audit trail."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_role
from ..models import (
    Agent,
    AuditEvent,
    Role,
    Run,
    RunStatus,
    Shipment,
    ShipmentStatus,
    Task,
    TaskStatus,
    User,
)
from ..schemas import MetricsOut

router = APIRouter(prefix="/api", tags=["observability"])


@router.get("/metrics", response_model=MetricsOut)
def metrics(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> MetricsOut:
    task_rows = db.execute(select(Task.status, func.count(Task.id)).group_by(Task.status)).all()
    tasks_by_status = {s.value: 0 for s in TaskStatus}
    for task_status, count in task_rows:
        tasks_by_status[task_status.value] = int(count)

    shipment_rows = db.execute(
        select(Shipment.status, func.count(Shipment.id)).group_by(Shipment.status)
    ).all()
    shipments_by_status = {s.value: 0 for s in ShipmentStatus}
    for shipment_status, count in shipment_rows:
        shipments_by_status[shipment_status.value] = int(count)

    runs_total = int(db.scalar(select(func.count(Run.id))) or 0)
    runs_failed = int(
        db.scalar(select(func.count(Run.id)).where(Run.status == RunStatus.failed)) or 0
    )
    tokens_used = int(db.scalar(select(func.coalesce(func.sum(Run.tokens_used), 0))) or 0)
    cost_usd = float(db.scalar(select(func.coalesce(func.sum(Run.cost_usd), 0.0))) or 0.0)

    busy_rows = db.execute(
        select(Agent.name, func.count(Run.id))
        .join(Run, Run.agent_id == Agent.id)
        .where(Run.status == RunStatus.running)
        .group_by(Agent.name)
    ).all()
    agents_busy = {name: int(count) for name, count in busy_rows}

    return MetricsOut(
        tasks_by_status=tasks_by_status,
        runs_total=runs_total,
        runs_failed=runs_failed,
        tokens_used=tokens_used,
        cost_usd=round(cost_usd, 6),
        agents_busy=agents_busy,
        shipments_by_status=shipments_by_status,
    )


@router.get("/audit", response_model=list[dict])
def audit_log(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(Role.admin)),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit))
    return [
        {
            "id": e.id,
            "actor_id": e.actor_id,
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "detail": e.detail,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]
