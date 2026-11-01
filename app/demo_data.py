"""Demo data: four agents and a handful of shipments.

Idempotent — running it twice does not duplicate anything.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal, init_db
from .models import Agent, AgentKind, Shipment

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
