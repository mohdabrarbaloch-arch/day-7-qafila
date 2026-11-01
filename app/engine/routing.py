"""Freight cost, transit-time and route scoring.

All arithmetic is deterministic and unit-tested. There is no model call here —
an agent that cannot explain its own number is not an agent you can audit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Cost model constants (PKR). Documented in docs/usage.md so a finance person
# can check the numbers without reading Python.
BASE_FEE_PKR = 250.0
PER_KM_PER_KG_PKR = 0.018
FUEL_SURCHARGE_RATE = 0.11

# Heavy freight gets a per-kg discount: the marginal cost of the 500th kg is
# lower than the 5th. Tiers are (upper_bound_kg, multiplier).
WEIGHT_TIERS: tuple[tuple[float, float], ...] = (
    (50.0, 1.00),
    (500.0, 0.92),
    (5_000.0, 0.84),
    (math.inf, 0.78),
)

# Average road speed by distance band (km/h). Long hauls run on motorways and
# average faster than city runs, which are dominated by stops.
SPEED_BANDS: tuple[tuple[float, float], ...] = (
    (50.0, 22.0),
    (300.0, 45.0),
    (1_000.0, 58.0),
    (math.inf, 52.0),
)

HANDLING_HOURS = 3.0


def weight_multiplier(weight_kg: float) -> float:
    """Per-kg rate multiplier for a shipment weight."""
    if weight_kg <= 0:
        raise ValueError("weight_kg must be positive")
    for upper, multiplier in WEIGHT_TIERS:
        if weight_kg <= upper:
            return multiplier
    return WEIGHT_TIERS[-1][1]


def average_speed_kmh(distance_km: float) -> float:
    if distance_km <= 0:
        raise ValueError("distance_km must be positive")
    for upper, speed in SPEED_BANDS:
        if distance_km <= upper:
            return speed
    return SPEED_BANDS[-1][1]


def freight_cost(weight_kg: float, distance_km: float) -> float:
    """Total freight cost in PKR, rounded to 2dp.

    cost = base + (per_km_per_kg * distance * weight * tier) * (1 + fuel)
    """
    if weight_kg <= 0 or distance_km <= 0:
        raise ValueError("weight_kg and distance_km must be positive")

    variable = PER_KM_PER_KG_PKR * distance_km * weight_kg * weight_multiplier(weight_kg)
    with_fuel = variable * (1 + FUEL_SURCHARGE_RATE)
    return round(BASE_FEE_PKR + with_fuel, 2)


def transit_hours(distance_km: float) -> float:
    """Driving time plus fixed handling, rounded to 1dp."""
    if distance_km <= 0:
        raise ValueError("distance_km must be positive")
    return round(distance_km / average_speed_kmh(distance_km) + HANDLING_HOURS, 1)


def slack_hours(distance_km: float, deadline_hours: float) -> float:
    """Hours of headroom. Negative means the shipment cannot make its deadline."""
    return round(deadline_hours - transit_hours(distance_km), 1)


def urgency_score(distance_km: float, deadline_hours: float) -> float:
    """0..1 where 1 is 'will miss the deadline if not moved now'.

    Ratio of required time to available time, clamped. A shipment needing 30h
    with 30h of deadline scores 1.0; one needing 10h with 60h scores ~0.17.
    """
    if deadline_hours <= 0:
        raise ValueError("deadline_hours must be positive")
    needed = transit_hours(distance_km)
    return round(min(1.0, needed / deadline_hours), 3)


@dataclass(frozen=True)
class RouteOption:
    name: str
    distance_km: float
    toll_pkr: float
    risk: float  # 0..1, higher is worse

    def score(self, weight_kg: float) -> float:
        """Lower is better: cost + risk penalty expressed in PKR."""
        cost = freight_cost(weight_kg, self.distance_km) + self.toll_pkr
        # A 0.1 risk step is priced at 4% of freight — a judgement call, but a
        # stated one, which is the point.
        return round(cost * (1 + self.risk * 0.4), 2)


def rank_routes(weight_kg: float, options: list[RouteOption]) -> list[dict]:
    """Rank candidate routes cheapest-first, with the reasoning attached."""
    if not options:
        raise ValueError("at least one route option is required")

    scored = []
    for option in options:
        scored.append(
            {
                "name": option.name,
                "distance_km": option.distance_km,
                "toll_pkr": option.toll_pkr,
                "risk": option.risk,
                "freight_pkr": freight_cost(weight_kg, option.distance_km),
                "transit_hours": transit_hours(option.distance_km),
                "score": option.score(weight_kg),
            }
        )
    scored.sort(key=lambda r: (r["score"], r["distance_km"]))
    for index, row in enumerate(scored, start=1):
        row["rank"] = index
    return scored
