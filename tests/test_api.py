"""API tests — auth, agents, tasks, fleet, shipments, dashboard."""


class TestAuth:
    def test_register_and_login(self, client):
        r = client.post("/api/auth/register", json={"email": "a@b.pk", "name": "Ayaan", "password": "pass1234"})
        assert r.status_code == 201
        assert r.json()["access_token"]
        r = client.post("/api/auth/login", json={"email": "a@b.pk", "password": "pass1234"})
        assert r.status_code == 200
        assert r.json()["user"]["email"] == "a@b.pk"

    def test_duplicate_email_conflict(self, client, auth_headers):
        r = client.post(
            "/api/auth/register", json={"email": "tester@qafila.pk", "name": "Xara", "password": "pass1234"}
        )
        assert r.status_code == 409

    def test_wrong_password_401(self, client):
        client.post("/api/auth/register", json={"email": "c@d.pk", "name": "Cora", "password": "pass1234"})
        r = client.post("/api/auth/login", json={"email": "c@d.pk", "password": "wrong123"})
        assert r.status_code == 401

    def test_weak_password_rejected(self, client):
        r = client.post("/api/auth/register", json={"email": "e@f.pk", "name": "Eli", "password": "short"})
        assert r.status_code == 422

    def test_me_requires_token(self, client):
        assert client.get("/api/auth/me").status_code == 401

    def test_me_returns_user(self, client, auth_headers):
        r = client.get("/api/auth/me", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["email"] == "tester@qafila.pk"


class TestAgents:
    def test_create_and_list(self, client, auth_headers):
        r = client.post("/api/agents", headers=auth_headers, json={"name": "Router", "kind": "route"})
        assert r.status_code == 201
        r = client.get("/api/agents", headers=auth_headers)
        assert len(r.json()) == 1
        assert r.json()[0]["kind"] == "route"

    def test_invalid_kind_422(self, client, auth_headers):
        r = client.post("/api/agents", headers=auth_headers, json={"name": "X", "kind": "teleport"})
        assert r.status_code == 422

    def test_agents_are_owner_scoped(self, client, auth_headers):
        client.post("/api/agents", headers=auth_headers, json={"name": "Mine", "kind": "dispatch"})
        other = client.post(
            "/api/auth/register", json={"email": "other@qafila.pk", "name": "Omar", "password": "pass1234"}
        )
        other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        r = client.get("/api/agents", headers=other_headers)
        assert r.json() == []

    def test_update_status(self, client, auth_headers, demo_agent):
        r = client.patch(f"/api/agents/{demo_agent['id']}", headers=auth_headers, json={"status": "running"})
        assert r.status_code == 200
        assert r.json()["status"] == "running"

    def test_delete(self, client, auth_headers, demo_agent):
        r = client.delete(f"/api/agents/{demo_agent['id']}", headers=auth_headers)
        assert r.status_code == 204
        assert client.get("/api/agents", headers=auth_headers).json() == []

    def test_get_missing_404(self, client, auth_headers):
        assert client.get("/api/agents/9999", headers=auth_headers).status_code == 404


class TestTasks:
    def test_create_and_run_dispatch_task(self, client, auth_headers, demo_agent):
        client.post(
            "/api/fleet",
            headers=auth_headers,
            json={"name": "Van", "vehicle_type": "van", "capacity_kg": 800, "cost_per_km": 40},
        )
        r = client.post(
            "/api/tasks",
            headers=auth_headers,
            json={
                "agent_id": demo_agent["id"],
                "title": "Dispatch to Lahore",
                "input_data": {"weight_kg": 100, "origin": "Karachi", "destination": "Lahore"},
            },
        )
        assert r.status_code == 201
        assert r.json()["status"] == "queued"
        r = client.post("/api/tasks/run", headers=auth_headers)
        assert r.json()["ran"] == 1
        tasks = client.get("/api/tasks", headers=auth_headers).json()
        assert tasks[0]["status"] == "done"
        assert tasks[0]["output_data"]["ok"] is True

    def test_task_requires_owned_agent(self, client, auth_headers):
        r = client.post(
            "/api/tasks", headers=auth_headers, json={"agent_id": 9999, "title": "Ghost task", "input_data": {}}
        )
        assert r.status_code == 404

    def test_failed_task_records_error(self, client, auth_headers, demo_agent):
        client.post(
            "/api/tasks",
            headers=auth_headers,
            json={"agent_id": demo_agent["id"], "title": "Bad", "input_data": {"weight_kg": 0}},
        )
        client.post("/api/tasks/run", headers=auth_headers)
        tasks = client.get("/api/tasks", headers=auth_headers).json()
        assert tasks[0]["status"] == "failed"
        assert tasks[0]["error"]


class TestFleet:
    def test_create_vehicle(self, client, auth_headers):
        r = client.post(
            "/api/fleet",
            headers=auth_headers,
            json={"name": "Truck-1", "vehicle_type": "truck", "capacity_kg": 5000, "cost_per_km": 90},
        )
        assert r.status_code == 201
        assert r.json()["status"] == "available"

    def test_invalid_type_422(self, client, auth_headers):
        r = client.post(
            "/api/fleet",
            headers=auth_headers,
            json={"name": "X", "vehicle_type": "plane", "capacity_kg": 1, "cost_per_km": 1},
        )
        assert r.status_code == 422


class TestShipments:
    def test_create_auto_dispatch(self, client, auth_headers):
        client.post(
            "/api/fleet",
            headers=auth_headers,
            json={"name": "Van", "vehicle_type": "van", "capacity_kg": 800, "cost_per_km": 40},
        )
        r = client.post(
            "/api/shipments",
            headers=auth_headers,
            json={"origin": "Karachi", "destination": "Lahore", "weight_kg": 100},
        )
        assert r.status_code == 201
        s = r.json()
        assert s["tracking_code"].startswith("QF-")
        assert s["status"] == "assigned"
        assert s["vehicle_id"] is not None
        assert s["cost"] > 0

    def test_advance_lifecycle(self, client, auth_headers):
        client.post(
            "/api/fleet",
            headers=auth_headers,
            json={"name": "Van", "vehicle_type": "van", "capacity_kg": 800, "cost_per_km": 40},
        )
        s = client.post(
            "/api/shipments",
            headers=auth_headers,
            json={"origin": "Karachi", "destination": "Hyderabad", "weight_kg": 50},
        ).json()
        r = client.post(f"/api/shipments/{s['id']}/advance", headers=auth_headers)
        assert r.json()["status"] == "in_transit"
        r = client.post(f"/api/shipments/{s['id']}/advance", headers=auth_headers)
        assert r.json()["status"] == "delivered"
        # vehicle freed
        vehicles = client.get("/api/fleet", headers=auth_headers).json()
        assert vehicles[0]["status"] == "available"

    def test_advance_delivered_rejected(self, client, auth_headers):
        client.post(
            "/api/fleet",
            headers=auth_headers,
            json={"name": "Van", "vehicle_type": "van", "capacity_kg": 800, "cost_per_km": 40},
        )
        s = client.post(
            "/api/shipments",
            headers=auth_headers,
            json={"origin": "Karachi", "destination": "Hyderabad", "weight_kg": 50},
        ).json()
        for _ in range(2):
            client.post(f"/api/shipments/{s['id']}/advance", headers=auth_headers)
        r = client.post(f"/api/shipments/{s['id']}/advance", headers=auth_headers)
        assert r.status_code == 400

    def test_shipment_owner_scoped(self, client, auth_headers):
        s = client.post(
            "/api/shipments",
            headers=auth_headers,
            json={"origin": "Karachi", "destination": "Hyderabad", "weight_kg": 10},
        ).json()
        other = client.post("/api/auth/register", json={"email": "z@qafila.pk", "name": "Zara", "password": "pass1234"})
        other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        assert client.get(f"/api/shipments/{s['id']}", headers=other_headers).status_code == 404


class TestDashboard:
    def test_dashboard_counts(self, client, auth_headers, demo_agent):
        client.post(
            "/api/fleet",
            headers=auth_headers,
            json={"name": "Van", "vehicle_type": "van", "capacity_kg": 800, "cost_per_km": 40},
        )
        client.post(
            "/api/shipments",
            headers=auth_headers,
            json={"origin": "Karachi", "destination": "Lahore", "weight_kg": 100},
        )
        d = client.get("/api/dashboard", headers=auth_headers).json()
        assert d["shipments_total"] == 1
        assert d["shipments_in_transit"] == 1
        assert d["fleet_available"] == 0
        assert d["fleet_on_route"] == 1
        assert d["agents_total"] == 1
        assert len(d["recent_events"]) >= 1

    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
