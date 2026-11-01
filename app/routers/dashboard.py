"""Dashboard routes — aggregate stats and recent events."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_current_user
from app.models import Agent, Event, Shipment, Task, User, Vehicle
from app.schemas import DashboardOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DashboardOut:
    shipments = db.query(Shipment).filter(Shipment.owner_id == user.id).all()
    agents = db.query(Agent).filter(Agent.owner_id == user.id).all()
    tasks = db.query(Task).join(Agent).filter(Agent.owner_id == user.id).all()
    vehicles = db.query(Vehicle).filter(Vehicle.owner_id == user.id).all()
    events = db.query(Event).filter(Event.owner_id == user.id).order_by(Event.created_at.desc()).limit(10).all()

    return DashboardOut(
        shipments_total=len(shipments),
        shipments_in_transit=sum(1 for s in shipments if s.status in ("assigned", "in_transit")),
        shipments_delivered=sum(1 for s in shipments if s.status == "delivered"),
        agents_total=len(agents),
        agents_running=sum(1 for a in agents if a.status == "running"),
        tasks_queued=sum(1 for t in tasks if t.status == "queued"),
        tasks_done=sum(1 for t in tasks if t.status == "done"),
        fleet_available=sum(1 for v in vehicles if v.status == "available"),
        fleet_on_route=sum(1 for v in vehicles if v.status == "on_route"),
        recent_events=[
            {"id": e.id, "kind": e.kind, "message": e.message, "created_at": e.created_at.isoformat()} for e in events
        ],
    )
