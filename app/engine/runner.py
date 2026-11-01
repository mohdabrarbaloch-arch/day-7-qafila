"""Synchronous task runner — executes queued agent tasks and records outcomes."""

import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.engine.logistics import build_context, run_agent
from app.models import Agent, Event, Task, Vehicle


def _agent_context(db: Session, owner_id: int) -> object:
    vehicles = db.query(Vehicle).filter(Vehicle.owner_id == owner_id).all()
    fleet = [
        {"id": v.id, "name": v.name, "status": v.status, "capacity_kg": v.capacity_kg, "cost_per_km": v.cost_per_km}
        for v in vehicles
    ]
    return build_context(fleet=fleet, shipments=[], inventory={}, demand_history=[])


def run_pending_tasks(db: Session, owner_id: int, limit: int = 20) -> int:
    """Execute up to `limit` queued tasks for the owner, oldest first. Returns count run."""
    tasks = (
        db.query(Task)
        .join(Agent)
        .filter(Agent.owner_id == owner_id, Task.status == "queued")
        .order_by(Task.created_at.asc())
        .limit(limit)
        .all()
    )
    if not tasks:
        return 0

    ctx = _agent_context(db, owner_id)
    now = datetime.now(UTC)
    ran = 0
    for task in tasks:
        task.status = "running"
        task.started_at = now
        db.flush()
        try:
            input_data = json.loads(task.input_data or "{}")
            output = run_agent(task.agent.kind, input_data, ctx)
            task.output_data = json.dumps(output)
            task.status = "done" if output.get("ok") else "failed"
            if not output.get("ok"):
                task.error = output.get("reason", "agent returned not-ok")
        except Exception as exc:  # noqa: BLE001 — task isolation
            task.status = "failed"
            task.error = str(exc)
        task.finished_at = datetime.now(UTC)
        db.add(Event(owner_id=owner_id, kind="task", message=f"Task #{task.id} '{task.title}' → {task.status}"))
        ran += 1
    db.commit()
    return ran
