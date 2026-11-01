"""Routing arithmetic. These are the numbers a finance team will check."""

from __future__ import annotations

import pytest

from app.engine import routing


def test_weight_multiplier_tiers():
    assert routing.weight_multiplier(10) == 1.00
    assert routing.weight_multiplier(50) == 1.00
    assert routing.weight_multiplier(51) == 0.92
    assert routing.weight_multiplier(500) == 0.92
    assert routing.weight_multiplier(501) == 0.84
    assert routing.weight_multiplier(5_000) == 0.84
    assert routing.weight_multiplier(5_001) == 0.78


def test_weight_multiplier_rejects_non_positive():
    with pytest.raises(ValueError):
        routing.weight_multiplier(0)
    with pytest.raises(ValueError):
        routing.weight_multiplier(-5)


def test_average_speed_bands():
    assert routing.average_speed_kmh(20) == 22.0
    assert routing.average_speed_kmh(50) == 22.0
    assert routing.average_speed_kmh(51) == 45.0
    assert routing.average_speed_kmh(300) == 45.0
    assert routing.average_speed_kmh(301) == 58.0
    assert routing.average_speed_kmh(1_000) == 58.0
    assert routing.average_speed_kmh(1_001) == 52.0


def test_freight_cost_matches_hand_calculation():
    # 320 kg -> 0.92 tier
    #   0.018 * 1240 = 22.32
    #   22.32 * 320  = 7142.40
    #   7142.40 * 0.92 = 6571.008
    #   6571.008 * 1.11 (fuel) = 7293.81888
    #   + 250 base = 7543.81888 -> 7543.82
    assert routing.freight_cost(320, 1240) == 7543.82


def test_freight_cost_is_monotonic_in_distance():
    short = routing.freight_cost(100, 100)
    long = routing.freight_cost(100, 1_000)
    assert long > short


def test_freight_cost_rejects_bad_input():
    with pytest.raises(ValueError):
        routing.freight_cost(0, 100)
    with pytest.raises(ValueError):
        routing.freight_cost(100, 0)


def test_transit_hours_includes_handling():
    # 1240 km at 52 km/h = 23.846... + 3 handling = 26.8
    assert routing.transit_hours(1240) == 26.8


def test_slack_hours_goes_negative_when_impossible():
    # 1240 km needs 26.8h; a 20h deadline cannot work.
    assert routing.slack_hours(1240, 20) < 0
    assert routing.slack_hours(1240, 48) > 0


def test_urgency_score_is_clamped_to_one():
    # Needs 26.8h with only 10h available -> clamped at 1.0
    assert routing.urgency_score(1240, 10) == 1.0
    # Needs 26.8h with 100h available -> ~0.268
    assert routing.urgency_score(1240, 100) == 0.268


def test_urgency_rejects_zero_deadline():
    with pytest.raises(ValueError):
        routing.urgency_score(100, 0)


def test_rank_routes_prefers_cheaper_option():
    options = [
        routing.RouteOption(name="direct", distance_km=1_000, toll_pkr=0, risk=0.3),
        routing.RouteOption(name="detour", distance_km=1_400, toll_pkr=0, risk=0.05),
    ]
    ranked = routing.rank_routes(100, options)
    assert ranked[0]["name"] == "direct"
    assert [r["rank"] for r in ranked] == [1, 2]


def test_rank_routes_risk_can_flip_the_winner():
    # The detour is longer but far safer; with a big risk penalty it should win.
    options = [
        routing.RouteOption(name="direct", distance_km=1_000, toll_pkr=0, risk=0.95),
        routing.RouteOption(name="detour", distance_km=1_050, toll_pkr=0, risk=0.0),
    ]
    ranked = routing.rank_routes(100, options)
    assert ranked[0]["name"] == "detour"


def test_rank_routes_requires_options():
    with pytest.raises(ValueError):
        routing.rank_routes(100, [])
