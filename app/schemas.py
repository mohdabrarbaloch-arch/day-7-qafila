"""Pydantic request/response schemas.

Field bounds here are the single source of truth for input validation — the
routers do not re-check them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import AgentKind, Role, RunStatus, ShipmentStatus, TaskStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth -----------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role


class UserOut(ORMModel):
    id: str
    email: EmailStr
    role: Role
    created_at: datetime


# --- agents ---------------------------------------------------------------


class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    kind: AgentKind
    description: str = Field(default="", max_length=2000)
    max_concurrency: int = Field(default=2, ge=1, le=16)


class AgentOut(ORMModel):
    id: str
    name: str
    kind: AgentKind
    description: str
    max_concurrency: int
    enabled: bool
    created_at: datetime


# --- shipments ------------------------------------------------------------


class ShipmentCreate(BaseModel):
    reference: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9\-_]+$")
    origin_city: str = Field(min_length=2, max_length=80)
    destination_city: str = Field(min_length=2, max_length=80)
    weight_kg: float = Field(gt=0, le=40_000)
    distance_km: float = Field(gt=0, le=20_000)
    deadline_hours: float = Field(default=48.0, gt=0, le=720)


class ShipmentOut(ORMModel):
    id: str
    reference: str
    origin_city: str
    destination_city: str
    weight_kg: float
    distance_km: float
    status: ShipmentStatus
    deadline_hours: float
    created_at: datetime


# --- tasks ----------------------------------------------------------------


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    kind: AgentKind
    priority: int = Field(default=5, ge=1, le=10)
    payload: dict[str, Any] = Field(default_factory=dict)
    shipment_id: str | None = None
    depends_on_id: str | None = None


class TaskOut(ORMModel):
    id: str
    title: str
    kind: AgentKind
    status: TaskStatus
    priority: int
    payload: dict[str, Any]
    shipment_id: str | None
    agent_id: str | None
    depends_on_id: str | None
    created_at: datetime
    updated_at: datetime


# --- runs -----------------------------------------------------------------


class RunOut(ORMModel):
    id: str
    task_id: str
    agent_id: str
    status: RunStatus
    steps: list[dict[str, Any]]
    tokens_used: int
    cost_usd: float
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class DispatchResult(BaseModel):
    dispatched: list[RunOut]
    skipped: list[dict[str, str]]
    message: str


class MetricsOut(BaseModel):
    tasks_by_status: dict[str, int]
    runs_total: int
    runs_failed: int
    tokens_used: int
    cost_usd: float
    agents_busy: dict[str, int]
    shipments_by_status: dict[str, int]
