"""Agent routes — CRUD for AI logistics agents."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_current_user
from app.engine.logistics import AGENT_DESCRIPTIONS
from app.models import Agent, User
from app.schemas import AgentCreate, AgentOut, AgentUpdate

router = APIRouter(prefix="/agents", tags=["agents"])


def _to_out(agent: Agent) -> AgentOut:
    return AgentOut(
        id=agent.id,
        name=agent.name,
        kind=agent.kind,
        description=agent.description,
        status=agent.status,
        config=json.loads(agent.config or "{}"),
        created_at=agent.created_at,
    )


@router.get("", response_model=list[AgentOut])
def list_agents(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[AgentOut]:
    agents = db.query(Agent).filter(Agent.owner_id == user.id).order_by(Agent.created_at.asc()).all()
    return [_to_out(a) for a in agents]


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AgentCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> AgentOut:
    agent = Agent(
        owner_id=user.id,
        name=payload.name.strip(),
        kind=payload.kind,
        description=payload.description.strip() or AGENT_DESCRIPTIONS.get(payload.kind, ""),
        config=json.dumps(payload.config),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return _to_out(agent)


@router.get("/kinds")
def agent_kinds() -> dict:
    return {"kinds": AGENT_DESCRIPTIONS}


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AgentOut:
    agent = db.get(Agent, agent_id)
    if agent is None or agent.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return _to_out(agent)


@router.patch("/{agent_id}", response_model=AgentOut)
def update_agent(
    agent_id: int, payload: AgentUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> AgentOut:
    agent = db.get(Agent, agent_id)
    if agent is None or agent.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if payload.name is not None:
        agent.name = payload.name.strip()
    if payload.description is not None:
        agent.description = payload.description.strip()
    if payload.status is not None:
        agent.status = payload.status
    if payload.config is not None:
        agent.config = json.dumps(payload.config)
    db.commit()
    db.refresh(agent)
    return _to_out(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    agent = db.get(Agent, agent_id)
    if agent is None or agent.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    db.delete(agent)
    db.commit()
