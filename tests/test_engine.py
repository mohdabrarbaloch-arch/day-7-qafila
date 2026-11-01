"""Unit tests for the logistics engine — pure functions, no DB."""

from app.engine.logistics import (
    AGENT_REGISTRY,
    build_context,
    demo_demand_history,
    demo_inventory,
    road_distance_km,
    run_agent,
    run_demand_agent,
    run_dispatch_agent,
    run_inventory_agent,
    run_route_agent,
)


def make_ctx(fleet=None, inventory=None, demand=None):
    return build_context(
        fleet=fleet or [],
        shipments=[],
        inventory=inventory or demo_inventory(),
        demand_history=demand or demo_demand_history(),
    )


class TestRoadDistance:
    def test_known_pair_symmetric(self):
        assert road_distance_km("Karachi", "Lahore") == 1210.0
        assert road_distance_km("Lahore", "Karachi") == 1210.0

    def test_same_city_zero(self):
        assert road_distance_km("Karachi", "Karachi") == 0.0

    def test_alias_normalization(self):
        assert road_distance_km("KHI", "LHR") == 1210.0

    def test_unknown_pair_deterministic(self):
        a = road_distance_km("Gwadar", "Skardu")
        b = road_distance_km("Gwadar", "Skardu")
        assert a == b
        assert a > 0


class TestDispatchAgent:
    def test_picks_cheapest_fitting_vehicle(self):
        ctx = make_ctx(
            fleet=[
                {"id": 1, "name": "Bike", "status": "available", "capacity_kg": 50, "cost_per_km": 15},
                {"id": 2, "name": "Van", "status": "available", "capacity_kg": 800, "cost_per_km": 40},
                {"id": 3, "name": "Truck", "status": "available", "capacity_kg": 5000, "cost_per_km": 90},
            ]
        )
        out = run_dispatch_agent({"weight_kg": 120, "origin": "Karachi", "destination": "Lahore"}, ctx)
        assert out["ok"] is True
        assert out["vehicle_id"] == 2  # van fits 120kg and is cheapest that fits
        assert out["distance_km"] == 1210.0
        assert out["cost"] == round(1210.0 * 40, 2)

    def test_ignores_unavailable_vehicles(self):
        ctx = make_ctx(
            fleet=[
                {"id": 1, "name": "Van", "status": "on_route", "capacity_kg": 800, "cost_per_km": 40},
                {"id": 2, "name": "Truck", "status": "available", "capacity_kg": 5000, "cost_per_km": 90},
            ]
        )
        out = run_dispatch_agent({"weight_kg": 100, "origin": "Karachi", "destination": "Lahore"}, ctx)
        assert out["ok"] is True
        assert out["vehicle_id"] == 2

    def test_no_vehicle_fits(self):
        ctx = make_ctx(fleet=[{"id": 1, "name": "Bike", "status": "available", "capacity_kg": 50, "cost_per_km": 15}])
        out = run_dispatch_agent({"weight_kg": 500, "origin": "Karachi", "destination": "Lahore"}, ctx)
        assert out["ok"] is False
        assert out["reason"] == "no_vehicle_fits"

    def test_rejects_zero_weight(self):
        out = run_dispatch_agent({"weight_kg": 0, "origin": "Karachi", "destination": "Lahore"}, make_ctx())
        assert out["ok"] is False


class TestRouteAgent:
    def test_direct_route_eta(self):
        out = run_route_agent({"origin": "Karachi", "destination": "Lahore", "speed_kmh": 60}, make_ctx())
        assert out["ok"] is True
        assert out["total_km"] == 1210.0
        assert out["eta_hours"] == round(1210.0 / 60, 1)

    def test_stopover_sums_legs(self):
        out = run_route_agent(
            {"origin": "Karachi", "destination": "Sukkur", "stopover": "Hyderabad", "speed_kmh": 60}, make_ctx()
        )
        assert out["ok"] is True
        assert len(out["legs"]) == 2
        assert out["total_km"] == 165.0 + 300.0

    def test_rejects_bad_speed(self):
        out = run_route_agent({"origin": "Karachi", "destination": "Lahore", "speed_kmh": 0}, make_ctx())
        assert out["ok"] is False


class TestInventoryAgent:
    def test_above_reorder_point(self):
        out = run_inventory_agent({"sku": "SKU-1001", "reorder_point": 10}, make_ctx())
        assert out["ok"] is True
        assert out["needs_reorder"] is False

    def test_below_reorder_point_suggests_qty(self):
        out = run_inventory_agent({"sku": "SKU-1002", "reorder_point": 10}, make_ctx())
        assert out["ok"] is True
        assert out["needs_reorder"] is True
        assert out["suggested_order_qty"] == 12.0  # 2*10 - 8

    def test_unknown_sku_treated_as_zero_stock(self):
        out = run_inventory_agent({"sku": "SKU-9999", "reorder_point": 5}, make_ctx())
        assert out["needs_reorder"] is True

    def test_rejects_missing_sku(self):
        out = run_inventory_agent({"reorder_point": 5}, make_ctx())
        assert out["ok"] is False


class TestDemandAgent:
    def test_moving_average_forecast(self):
        ctx = make_ctx(
            demand=[
                {"sku": "X", "qty": 10, "day": 1},
                {"sku": "X", "qty": 20, "day": 2},
                {"sku": "X", "qty": 30, "day": 3},
            ]
        )
        out = run_demand_agent({"sku": "X", "window": 3}, ctx)
        assert out["ok"] is True
        assert out["forecast"] == 20.0
        assert out["trend"] == "up"

    def test_no_history_flat(self):
        out = run_demand_agent({"sku": "NOPE", "window": 7}, make_ctx())
        assert out["ok"] is True
        assert out["forecast"] == 0.0
        assert out["trend"] == "flat"

    def test_rejects_bad_window(self):
        out = run_demand_agent({"sku": "X", "window": 0}, make_ctx())
        assert out["ok"] is False


class TestRegistry:
    def test_all_kinds_registered(self):
        assert set(AGENT_REGISTRY) == {"dispatch", "route", "inventory", "demand"}

    def test_unknown_kind(self):
        out = run_agent("teleport", {}, make_ctx())
        assert out["ok"] is False
        assert "unknown" in out["reason"]
