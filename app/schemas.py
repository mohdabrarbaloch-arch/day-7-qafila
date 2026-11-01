"""Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------- Auth ----------
class RegisterRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("password must contain at least one digit")
        if not any(c.isalpha() for c in v):
            raise ValueError("password must contain at least one letter")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Agents ----------
class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    kind: str = Field(pattern="^(dispatch|route|inventory|demand)$")
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = Field(default=None, pattern="^(idle|running|paused)$")
    config: dict[str, Any] | None = None


class AgentOut(BaseModel):
    id: int
    name: str
    kind: str
    description: str
    status: str
    config: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Tasks ----------
class TaskCreate(BaseModel):
    agent_id: int
    title: str = Field(min_length=2, max_length=200)
    input_data: dict[str, Any] = Field(default_factory=dict)


class TaskOut(BaseModel):
    id: int
    agent_id: int
    title: str
    status: str
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    error: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


# ---------- Fleet ----------
class VehicleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    vehicle_type: str = Field(pattern="^(bike|van|truck)$")
    capacity_kg: float = Field(gt=0, le=100_000)
    cost_per_km: float = Field(ge=0, le=10_000)


class VehicleOut(BaseModel):
    id: int
    name: str
    vehicle_type: str
    capacity_kg: float
    status: str
    location: str
    cost_per_km: float
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Shipments ----------
class ShipmentCreate(BaseModel):
    origin: str = Field(min_length=2, max_length=200)
    destination: str = Field(min_length=2, max_length=200)
    weight_kg: float = Field(gt=0, le=100_000)


class ShipmentOut(BaseModel):
    id: int
    tracking_code: str
    origin: str
    destination: str
    weight_kg: float
    status: str
    vehicle_id: int | None
    assigned_agent_id: int | None
    eta_hours: float
    cost: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------- Dashboard ----------
class DashboardOut(BaseModel):
    shipments_total: int
    shipments_in_transit: int
    shipments_delivered: int
    agents_total: int
    agents_running: int
    tasks_queued: int
    tasks_done: int
    fleet_available: int
    fleet_on_route: int
    recent_events: list[dict[str, Any]]
