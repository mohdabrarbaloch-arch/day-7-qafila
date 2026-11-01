"""Seed data: four agents, a handful of shipments, and the demo account.

Idempotent — running it twice does not duplicate anything. Called on startup
when SEED_DEMO_DATA is true.

The demo user is only created when DEMO_PASSWORD is set. A deployed instance
with an empty DEMO_PASSWORD therefore has no known login at all.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Agent, AgentKind, Role, Shipment, User
from .security import hash_password

AGENTS = [
    {
        "name": "Tarmeem",
        "kind": AgentKind.dispatcher,
        "description": "Reads a shipment, prices it, and decides whether it can make its deadline.",
        "max_concurrency": 3,
    },
    {
        "name": "Raasta",
        "kind": AgentKind.route_optimizer,
        "description": "Ranks candidate routes on cost, tolls and risk, and explains the pick.",
        "max_concurrency": 2,
    },
    {
        "name": "Ginti",
        "kind": AgentKind.inventory_auditor,
        "description": "Compares a manifest against stock on hand and raises shortages.",
        "max_concurrency": 2,
    },
    {
        "name": "Nigraan",
        "kind": AgentKind.exception_handler,
        "description": "Triages incident reports into a severity and a next action.",
        "max_concurrency": 4,
    },
]

SHIPMENTS = [
    {
        "reference": "QFL-1001",
        "origin_city": "Karachi",
        "destination_city": "Lahore",
        "weight_kg": 320.0,
        "distance_km": 1_240.0,
        "deadline_hours": 30.0,
    },
    {
        "reference": "QFL-1002",
        "origin_city": "Karachi",
        "destination_city": "Hyderabad",
        "weight_kg": 45.0,
        "distance_km": 165.0,
        "deadline_hours": 12.0,
    },
    {
        "reference": "QFL-1003",
        "origin_city": "Lahore",
        "destination_city": "Islamabad",
        "weight_kg": 1_800.0,
        "distance_km": 375.0,
        "deadline_hours": 24.0,
    },
    {
        "reference": "QFL-1004",
        "origin_city": "Quetta",
        "destination_city": "Karachi",
        "weight_kg": 90.0,
        "distance_km": 690.0,
        "deadline_hours": 20.0,
    },
]


def seed(db: Session) -> dict[str, int]:
    created = {"agents": 0, "shipments": 0, "users": 0}

    for spec in AGENTS:
        if db.scalar(select(Agent).where(Agent.name == spec["name"])) is None:
            db.add(Agent(**spec))
            created["agents"] += 1

    for spec in SHIPMENTS:
        if db.scalar(select(Shipment).where(Shipment.reference == spec["reference"])) is None:
            db.add(Shipment(**spec))
            created["shipments"] += 1

    settings = get_settings()
    if settings.demo_password:
        email = settings.demo_email.lower()
        if db.scalar(select(User).where(User.email == email)) is None:
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(settings.demo_password),
                    role=Role.admin,
                )
            )
            created["users"] += 1

    db.commit()
    return created
