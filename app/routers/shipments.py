"""Shipment routes — create shipments, auto-dispatch via the dispatch agent, track status."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_current_user
from app.engine.logistics import build_context, run_agent
from app.models import Event, Shipment, User, Vehicle
from app.schemas import ShipmentCreate, ShipmentOut

router = APIRouter(prefix="/shipments", tags=["shipments"])


def _to_out(s: Shipment) -> ShipmentOut:
    return ShipmentOut(
        id=s.id,
        tracking_code=s.tracking_code,
        origin=s.origin,
        destination=s.destination,
        weight_kg=s.weight_kg,
        status=s.status,
        vehicle_id=s.vehicle_id,
        assigned_agent_id=s.assigned_agent_id,
        eta_hours=s.eta_hours,
        cost=s.cost,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _dispatch_shipment(db: Session, shipment: Shipment) -> None:
    """Ask the dispatch agent to assign a vehicle; apply the result."""
    vehicles = db.query(Vehicle).filter(Vehicle.owner_id == shipment.owner_id).all()
    fleet = [
        {"id": v.id, "name": v.name, "status": v.status, "capacity_kg": v.capacity_kg, "cost_per_km": v.cost_per_km}
        for v in vehicles
    ]
    ctx = build_context(fleet=fleet, shipments=[], inventory={}, demand_history=[])
    result = run_agent(
        "dispatch",
        {"weight_kg": shipment.weight_kg, "origin": shipment.origin, "destination": shipment.destination},
        ctx,
    )
    if result.get("ok"):
        shipment.vehicle_id = result["vehicle_id"]
        shipment.eta_hours = result["eta_hours"]
        shipment.cost = result["cost"]
        shipment.status = "assigned"
        vehicle = db.get(Vehicle, result["vehicle_id"])
        if vehicle:
            vehicle.status = "on_route"
        db.add(
            Event(
                owner_id=shipment.owner_id,
                kind="dispatch",
                message=f"Shipment {shipment.tracking_code} → {result['vehicle_name']} (PKR {result['cost']})",
            )
        )
    else:
        shipment.status = "created"
        db.add(
            Event(
                owner_id=shipment.owner_id,
                kind="dispatch",
                message=f"Shipment {shipment.tracking_code}: {result.get('reason', 'no vehicle')}",
            )
        )


@router.get("", response_model=list[ShipmentOut])
def list_shipments(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ShipmentOut]:
    shipments = (
        db.query(Shipment).filter(Shipment.owner_id == user.id).order_by(Shipment.created_at.desc()).limit(100).all()
    )
    return [_to_out(s) for s in shipments]


@router.post("", response_model=ShipmentOut, status_code=status.HTTP_201_CREATED)
def create_shipment(
    payload: ShipmentCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ShipmentOut:
    shipment = Shipment(
        owner_id=user.id,
        tracking_code="QF-" + secrets.token_hex(4).upper(),
        origin=payload.origin.strip(),
        destination=payload.destination.strip(),
        weight_kg=payload.weight_kg,
    )
    db.add(shipment)
    db.flush()
    _dispatch_shipment(db, shipment)
    db.commit()
    db.refresh(shipment)
    return _to_out(shipment)


@router.get("/{shipment_id}", response_model=ShipmentOut)
def get_shipment(
    shipment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ShipmentOut:
    shipment = db.get(Shipment, shipment_id)
    if shipment is None or shipment.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
    return _to_out(shipment)


@router.post("/{shipment_id}/advance", response_model=ShipmentOut)
def advance_shipment(
    shipment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ShipmentOut:
    """Move a shipment through its lifecycle: assigned → in_transit → delivered."""
    shipment = db.get(Shipment, shipment_id)
    if shipment is None or shipment.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
    order = ["created", "assigned", "in_transit", "delivered"]
    if shipment.status not in order:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot advance from {shipment.status}")
    idx = order.index(shipment.status)
    if idx >= len(order) - 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shipment already delivered")
    shipment.status = order[idx + 1]
    if shipment.status == "delivered" and shipment.vehicle_id:
        vehicle = db.get(Vehicle, shipment.vehicle_id)
        if vehicle:
            vehicle.status = "available"
    db.add(Event(owner_id=user.id, kind="shipment", message=f"Shipment {shipment.tracking_code} → {shipment.status}"))
    db.commit()
    db.refresh(shipment)
    return _to_out(shipment)
