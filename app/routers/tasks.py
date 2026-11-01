"""Task routes — create tasks for agents, run the queue, list results."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_current_user
from app.engine.runner import run_pending_tasks
from app.models import Agent, Task, User
from app.schemas import TaskCreate, TaskOut

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _to_out(task: Task) -> TaskOut:
    return TaskOut(
        id=task.id,
        agent_id=task.agent_id,
        title=task.title,
        status=task.status,
        input_data=json.loads(task.input_data or "{}"),
        output_data=json.loads(task.output_data or "{}"),
        error=task.error,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
    )


@router.get("", response_model=list[TaskOut])
def list_tasks(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[TaskOut]:
    tasks = (
        db.query(Task).join(Agent).filter(Agent.owner_id == user.id).order_by(Task.created_at.desc()).limit(100).all()
    )
    return [_to_out(t) for t in tasks]


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TaskOut:
    agent = db.get(Agent, payload.agent_id)
    if agent is None or agent.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    task = Task(
        agent_id=agent.id,
        title=payload.title.strip(),
        input_data=json.dumps(payload.input_data),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _to_out(task)


@router.post("/run", response_model=dict)
def run_queue(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ran = run_pending_tasks(db, user.id)
    return {"ran": ran}


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TaskOut:
    task = db.get(Task, task_id)
    if task is None or task.agent.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return _to_out(task)
