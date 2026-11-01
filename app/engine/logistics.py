"""Qafila logistics engine — deterministic agent logic for dispatch, routing, inventory and demand.

Every agent is a pure function of (input_data, context) -> output_data so it can be unit-tested
without a database and executed synchronously by the task runner.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Distance model
# ---------------------------------------------------------------------------

# Rough inter-city road distances (km) for the demo network.
ROAD_DISTANCES_KM: dict[tuple[str, str], float] = {
    ("Karachi", "Hyderabad"): 165.0,
    ("Karachi", "Lahore"): 1210.0,
    ("Karachi", "Islamabad"): 1410.0,
    ("Karachi", "Quetta"): 690.0,
    ("Karachi", "Peshawar"): 1520.0,
    ("Lahore", "Islamabad"): 375.0,
    ("Lahore", "Faisalabad"): 130.0,
    ("Lahore", "Multan"): 330.0,
    ("Lahore", "Peshawar"): 500.0,
    ("Islamabad", "Peshawar"): 160.0,
    ("Islamabad", "Faisalabad"): 300.0,
    ("Faisalabad", "Multan"): 200.0,
    ("Multan", "Quetta"): 560.0,
    ("Hyderabad", "Quetta"): 520.0,
    ("Hyderabad", "Sukkur"): 300.0,
    ("Sukkur", "Multan"): 400.0,
    ("Sukkur", "Quetta"): 380.0,
    ("Karachi", "Sukkur"): 460.0,
}

CITY_ALIASES: dict[str, str] = {
    "khi": "Karachi",
    "karachi": "Karachi",
    "karchi": "Karachi",
    "hyd": "Hyderabad",
    "hyderabad": "Hyderabad",
    "lhr": "Lahore",
    "lahore": "Lahore",
    "isb": "Islamabad",
    "islamabad": "Islamabad",
    "rawalpindi": "Islamabad",
    "quetta": "Quetta",
    "psh": "Peshawar",
    "peshawar": "Peshawar",
    "fsd": "Faisalabad",
    "faisalabad": "Faisalabad",
    "multan": "Multan",
    "sukkur": "Sukkur",
}


def normalize_city(name: str) -> str:
    key = re.sub(r"[^a-z]", "", name.lower())
    return CITY_ALIASES.get(key, name.strip().title())


def road_distance_km(origin: str, destination: str) -> float:
    a, b = normalize_city(origin), normalize_city(destination)
    if a == b:
        return 0.0
    direct = ROAD_DISTANCES_KM.get((a, b)) or ROAD_DISTANCES_KM.get((b, a))
    if direct is not None:
        return direct
    # Fallback: great-circle estimate via Karachi hub.
    return 700.0 + (hash(a) % 400)  # deterministic pseudo-distance for unknown pairs


# ---------------------------------------------------------------------------
# Agent context
# ---------------------------------------------------------------------------


@dataclass
class AgentContext:
    """Read-only context passed to every agent run."""

    fleet: list[dict[str, Any]]  # available vehicles
    shipments: list[dict[str, Any]]  # recent shipments
    inventory: dict[str, float]  # sku -> stock level
    demand_history: list[dict[str, Any]]  # {sku, qty, day}


# ---------------------------------------------------------------------------
# Agent implementations
# ---------------------------------------------------------------------------


def run_dispatch_agent(input_data: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    """Pick the cheapest available vehicle that fits the shipment weight."""
    weight = float(input_data.get("weight_kg", 0))
    origin = str(input_data.get("origin", ""))
    destination = str(input_data.get("destination", ""))

    if weight <= 0:
        return {"ok": False, "reason": "weight_kg must be positive"}
    if not origin or not destination:
        return {"ok": False, "reason": "origin and destination are required"}

    candidates = [v for v in ctx.fleet if v.get("status") == "available" and v.get("capacity_kg", 0) >= weight]
    if not candidates:
        return {"ok": False, "reason": "no_vehicle_fits", "weight_kg": weight}

    best = min(candidates, key=lambda v: v.get("cost_per_km", 0))
    distance = road_distance_km(origin, destination)
    cost = round(distance * best.get("cost_per_km", 0), 2)
    return {
        "ok": True,
        "vehicle_id": best["id"],
        "vehicle_name": best.get("name"),
        "distance_km": round(distance, 1),
        "cost": cost,
        "eta_hours": round(distance / 60.0, 1),  # 60 km/h average
    }


def run_route_agent(input_data: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    """Compute ETA and cost for a route, optionally with a stopover."""
    origin = str(input_data.get("origin", ""))
    destination = str(input_data.get("destination", ""))
    stopover = str(input_data.get("stopover", ""))
    speed_kmh = float(input_data.get("speed_kmh", 60))

    if not origin or not destination:
        return {"ok": False, "reason": "origin and destination are required"}
    if speed_kmh <= 0:
        return {"ok": False, "reason": "speed_kmh must be positive"}

    legs = [(origin, destination)]
    if stopover:
        legs = [(origin, stopover), (stopover, destination)]

    total_km = sum(road_distance_km(a, b) for a, b in legs)
    eta_hours = round(total_km / speed_kmh, 1)
    return {
        "ok": True,
        "legs": [{"from": a, "to": b, "km": round(road_distance_km(a, b), 1)} for a, b in legs],
        "total_km": round(total_km, 1),
        "eta_hours": eta_hours,
        "eta_minutes": round(eta_hours * 60),
    }


def run_inventory_agent(input_data: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    """Flag SKUs below reorder point and suggest reorder quantities."""
    sku = str(input_data.get("sku", ""))
    reorder_point = float(input_data.get("reorder_point", 10))

    if not sku:
        return {"ok": False, "reason": "sku is required"}
    if reorder_point < 0:
        return {"ok": False, "reason": "reorder_point must be non-negative"}

    stock = ctx.inventory.get(sku, 0.0)
    if stock >= reorder_point:
        return {"ok": True, "sku": sku, "stock": stock, "needs_reorder": False}
    suggested = round(reorder_point * 2 - stock, 1)
    return {
        "ok": True,
        "sku": sku,
        "stock": stock,
        "needs_reorder": True,
        "suggested_order_qty": suggested,
    }


def run_demand_agent(input_data: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    """Simple moving-average forecast from demand history."""
    sku = str(input_data.get("sku", ""))
    window = int(input_data.get("window", 7))

    if not sku:
        return {"ok": False, "reason": "sku is required"}
    if window <= 0:
        return {"ok": False, "reason": "window must be positive"}

    history = [h for h in ctx.demand_history if h.get("sku") == sku]
    recent = history[-window:]
    if not recent:
        return {"ok": True, "sku": sku, "forecast": 0.0, "samples": 0, "trend": "flat"}

    values = [float(h.get("qty", 0)) for h in recent]
    forecast = round(sum(values) / len(values), 1)
    trend = "up" if values[-1] > values[0] else ("down" if values[-1] < values[0] else "flat")
    return {"ok": True, "sku": sku, "forecast": forecast, "samples": len(values), "trend": trend}


AGENT_REGISTRY: dict[str, Callable[[dict[str, Any], AgentContext], dict[str, Any]]] = {
    "dispatch": run_dispatch_agent,
    "route": run_route_agent,
    "inventory": run_inventory_agent,
    "demand": run_demand_agent,
}

AGENT_DESCRIPTIONS: dict[str, str] = {
    "dispatch": "Assigns shipments to the cheapest available vehicle that fits the load.",
    "route": "Computes distance, ETA and cost for a route, with optional stopovers.",
    "inventory": "Monitors stock levels and flags SKUs that need reordering.",
    "demand": "Forecasts demand from recent sales history using a moving average.",
}


def run_agent(kind: str, input_data: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    fn = AGENT_REGISTRY.get(kind)
    if fn is None:
        return {"ok": False, "reason": f"unknown agent kind: {kind}"}
    return fn(input_data, ctx)


def build_context(
    fleet: list[dict[str, Any]],
    shipments: list[dict[str, Any]],
    inventory: dict[str, float],
    demand_history: list[dict[str, Any]],
) -> AgentContext:
    return AgentContext(fleet=fleet, shipments=shipments, inventory=inventory, demand_history=demand_history)


# ---------------------------------------------------------------------------
# Demo data generators (deterministic, seeded)
# ---------------------------------------------------------------------------


def demo_inventory() -> dict[str, float]:
    return {
        "SKU-1001": 42.0,
        "SKU-1002": 8.0,
        "SKU-1003": 120.0,
        "SKU-1004": 3.0,
        "SKU-1005": 65.0,
        "SKU-1006": 15.0,
    }


def demo_demand_history() -> list[dict[str, Any]]:
    rng = random.Random(7)
    out: list[dict[str, Any]] = []
    for day in range(1, 15):
        for sku in ("SKU-1001", "SKU-1002", "SKU-1003"):
            out.append({"sku": sku, "qty": rng.randint(2, 20), "day": day})
    return out
