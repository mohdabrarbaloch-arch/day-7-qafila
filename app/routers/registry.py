"""Agent registry and shipment CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_role
from ..models import Agent, AuditEvent, Role, Shipment, ShipmentStatus, User
from ..schemas import AgentCreate, AgentOut, ShipmentCreate, ShipmentOut

router = APIRouter(prefix="/api", tags=["registry"])


@router.get("/agents", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[Agent]:
    return list(db.scalars(select(Agent).order_by(Agent.name)))


@router.post("/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AgentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.admin)),
) -> Agent:
    if db.scalar(select(Agent).where(Agent.name == payload.name)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An agent named '{payload.name}' already exists.",
        )
    agent = Agent(**payload.model_dump())
    db.add(agent)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="agent.created",
            entity_type="agent",
            entity_id=agent.id,
            detail={"name": agent.name, "kind": agent.kind.value},
        )
    )
    db.commit()
    db.refresh(agent)
    return agent


@router.patch("/agents/{agent_id}/toggle", response_model=AgentOut)
def toggle_agent(
    agent_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.admin)),
) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    agent.enabled = not agent.enabled
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="agent.toggled",
            entity_type="agent",
            entity_id=agent.id,
            detail={"enabled": agent.enabled},
        )
    )
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/shipments", response_model=list[ShipmentOut])
def list_shipments(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    shipment_status: ShipmentStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Shipment]:
    stmt = select(Shipment).order_by(Shipment.created_at.desc()).limit(limit)
    if shipment_status is not None:
        stmt = stmt.where(Shipment.status == shipment_status)
    return list(db.scalars(stmt))


@router.post("/shipments", response_model=ShipmentOut, status_code=status.HTTP_201_CREATED)
def create_shipment(
    payload: ShipmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.operator)),
) -> Shipment:
    if db.scalar(select(Shipment).where(Shipment.reference == payload.reference)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Shipment reference '{payload.reference}' is already in use.",
        )
    shipment = Shipment(**payload.model_dump())
    db.add(shipment)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="shipment.created",
            entity_type="shipment",
            entity_id=shipment.id,
            detail={"reference": shipment.reference},
        )
    )
    db.commit()
    db.refresh(shipment)
    return shipment


@router.get("/shipments/{shipment_id}", response_model=ShipmentOut)
def get_shipment(
    shipment_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> Shipment:
    shipment = db.get(Shipment, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found.")
    return shipment
