"""Fleet routes — vehicle CRUD."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_current_user
from app.models import User, Vehicle
from app.schemas import VehicleCreate, VehicleOut

router = APIRouter(prefix="/fleet", tags=["fleet"])


@router.get("", response_model=list[VehicleOut])
def list_vehicles(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[VehicleOut]:
    vehicles = db.query(Vehicle).filter(Vehicle.owner_id == user.id).order_by(Vehicle.created_at.asc()).all()
    return [VehicleOut.model_validate(v) for v in vehicles]


@router.post("", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
def create_vehicle(
    payload: VehicleCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> VehicleOut:
    vehicle = Vehicle(
        owner_id=user.id,
        name=payload.name.strip(),
        vehicle_type=payload.vehicle_type,
        capacity_kg=payload.capacity_kg,
        cost_per_km=payload.cost_per_km,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return VehicleOut.model_validate(vehicle)


@router.patch("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(
    vehicle_id: int, payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> VehicleOut:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    for field in ("status", "location"):
        if field in payload:
            setattr(vehicle, field, str(payload[field]))
    db.commit()
    db.refresh(vehicle)
    return VehicleOut.model_validate(vehicle)


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(vehicle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    db.delete(vehicle)
    db.commit()
