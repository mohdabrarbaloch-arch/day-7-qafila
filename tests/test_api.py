"""API behaviour: auth, roles, validation, dispatch, metrics."""

from __future__ import annotations


def test_health_is_public(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_register_creates_viewer_not_admin(client):
    res = client.post(
        "/api/auth/register",
        json={"email": "new@test.pk", "password": "a-good-password"},
    )
    assert res.status_code == 201
    assert res.json()["role"] == "viewer"


def test_register_rejects_duplicate_email(client, admin_user):
    res = client.post(
        "/api/auth/register",
        json={"email": "admin@test.pk", "password": "another-password"},
    )
    assert res.status_code == 409


def test_register_rejects_short_password(client):
    res = client.post("/api/auth/register", json={"email": "x@test.pk", "password": "short"})
    assert res.status_code == 422


def test_login_wrong_password_is_401(client, admin_user):
    res = client.post(
        "/api/auth/login", json={"email": "admin@test.pk", "password": "wrong-password"}
    )
    assert res.status_code == 401


def test_login_unknown_user_gives_same_message(client):
    res = client.post(
        "/api/auth/login", json={"email": "ghost@test.pk", "password": "whatever-123"}
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "Incorrect email or password."


def test_me_requires_a_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_the_caller(client, auth_headers):
    res = client.get("/api/auth/me", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["email"] == "admin@test.pk"


def test_garbage_token_is_401(client):
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert res.status_code == 401


def test_viewer_cannot_create_shipment(client, viewer_headers):
    res = client.post(
        "/api/shipments",
        headers=viewer_headers,
        json={
            "reference": "QFL-V-1",
            "origin_city": "Karachi",
            "destination_city": "Lahore",
            "weight_kg": 10,
            "distance_km": 100,
        },
    )
    assert res.status_code == 403


def test_operator_can_create_shipment(client, auth_headers):
    res = client.post(
        "/api/shipments",
        headers=auth_headers,
        json={
            "reference": "QFL-OK-1",
            "origin_city": "Karachi",
            "destination_city": "Lahore",
            "weight_kg": 120,
            "distance_km": 1240,
            "deadline_hours": 48,
        },
    )
    assert res.status_code == 201
    assert res.json()["status"] == "created"


def test_duplicate_shipment_reference_is_409(client, auth_headers):
    payload = {
        "reference": "QFL-DUP",
        "origin_city": "Karachi",
        "destination_city": "Quetta",
        "weight_kg": 50,
        "distance_km": 690,
    }
    assert client.post("/api/shipments", headers=auth_headers, json=payload).status_code == 201
    assert client.post("/api/shipments", headers=auth_headers, json=payload).status_code == 409


def test_shipment_rejects_negative_weight(client, auth_headers):
    res = client.post(
        "/api/shipments",
        headers=auth_headers,
        json={
            "reference": "QFL-BAD",
            "origin_city": "Karachi",
            "destination_city": "Lahore",
            "weight_kg": -5,
            "distance_km": 100,
        },
    )
    assert res.status_code == 422


def test_shipment_rejects_bad_reference_characters(client, auth_headers):
    res = client.post(
        "/api/shipments",
        headers=auth_headers,
        json={
            "reference": "QFL 1005!",
            "origin_city": "Karachi",
            "destination_city": "Lahore",
            "weight_kg": 10,
            "distance_km": 100,
        },
    )
    assert res.status_code == 422


def test_task_with_unknown_shipment_is_422(client, auth_headers):
    res = client.post(
        "/api/tasks",
        headers=auth_headers,
        json={"title": "Dispatch ghost", "kind": "dispatcher", "shipment_id": "nope"},
    )
    assert res.status_code == 422


def test_dispatch_runs_a_task_and_records_steps(client, auth_headers, seeded):
    shipment = seeded["shipment"]
    created = client.post(
        "/api/tasks",
        headers=auth_headers,
        json={
            "title": "Dispatch QFL-TEST-1",
            "kind": "dispatcher",
            "priority": 1,
            "shipment_id": shipment.id,
        },
    )
    assert created.status_code == 201

    result = client.post("/api/tasks/dispatch", headers=auth_headers)
    assert result.status_code == 200
    body = result.json()
    assert len(body["dispatched"]) == 1

    run = body["dispatched"][0]
    assert run["status"] == "succeeded"
    assert len(run["steps"]) >= 3
    assert run["tokens_used"] > 0
    assert run["cost_usd"] > 0


def test_dispatch_marks_at_risk_shipment_delayed(client, auth_headers, seeded):
    # 1240 km needs 26.8h; a 10h deadline cannot be met.
    client.post(
        "/api/shipments",
        headers=auth_headers,
        json={
            "reference": "QFL-TIGHT",
            "origin_city": "Karachi",
            "destination_city": "Lahore",
            "weight_kg": 100,
            "distance_km": 1240,
            "deadline_hours": 10,
        },
    )
    shipments = client.get("/api/shipments", headers=auth_headers).json()
    tight = next(s for s in shipments if s["reference"] == "QFL-TIGHT")

    client.post(
        "/api/tasks",
        headers=auth_headers,
        json={"title": "Dispatch tight", "kind": "dispatcher", "shipment_id": tight["id"]},
    )
    client.post("/api/tasks/dispatch", headers=auth_headers)

    after = client.get(f"/api/shipments/{tight['id']}", headers=auth_headers).json()
    assert after["status"] == "delayed"


def test_dispatch_skips_when_no_agent_of_that_kind(client, auth_headers, seeded):
    # Remove every route_optimizer by disabling them.
    for agent in seeded["agents"]:
        if agent.kind.value == "route_optimizer":
            client.patch(f"/api/agents/{agent.id}/toggle", headers=auth_headers)

    client.post(
        "/api/tasks",
        headers=auth_headers,
        json={"title": "Optimise", "kind": "route_optimizer", "shipment_id": seeded["shipment"].id},
    )
    body = client.post("/api/tasks/dispatch", headers=auth_headers).json()
    assert body["dispatched"] == []
    assert any("disabled" in s["reason"] for s in body["skipped"])


def test_dependency_blocks_dispatch_until_parent_succeeds(client, auth_headers, seeded):
    parent = client.post(
        "/api/tasks",
        headers=auth_headers,
        json={"title": "Parent", "kind": "dispatcher", "shipment_id": seeded["shipment"].id},
    ).json()

    child = client.post(
        "/api/tasks",
        headers=auth_headers,
        json={
            "title": "Child",
            "kind": "route_optimizer",
            "shipment_id": seeded["shipment"].id,
            "depends_on_id": parent["id"],
        },
    ).json()

    # First dispatch: parent runs, child is still blocked.
    first = client.post("/api/tasks/dispatch", headers=auth_headers).json()
    assert len(first["dispatched"]) == 1
    assert any(s["task_id"] == child["id"] for s in first["skipped"])

    # Second dispatch: parent succeeded, so the child is now runnable.
    second = client.post("/api/tasks/dispatch", headers=auth_headers).json()
    assert len(second["dispatched"]) == 1


def test_metrics_reflect_completed_runs(client, auth_headers, seeded):
    client.post(
        "/api/tasks",
        headers=auth_headers,
        json={"title": "Dispatch", "kind": "dispatcher", "shipment_id": seeded["shipment"].id},
    )
    client.post("/api/tasks/dispatch", headers=auth_headers)

    metrics = client.get("/api/metrics", headers=auth_headers).json()
    assert metrics["runs_total"] == 1
    assert metrics["tasks_by_status"]["succeeded"] == 1
    assert metrics["tokens_used"] > 0


def test_audit_log_is_admin_only(client, auth_headers, viewer_headers):
    assert client.get("/api/audit", headers=viewer_headers).status_code == 403
    assert client.get("/api/audit", headers=auth_headers).status_code == 200


def test_audit_records_shipment_creation(client, auth_headers):
    client.post(
        "/api/shipments",
        headers=auth_headers,
        json={
            "reference": "QFL-AUDIT",
            "origin_city": "Karachi",
            "destination_city": "Lahore",
            "weight_kg": 10,
            "distance_km": 100,
        },
    )
    events = client.get("/api/audit", headers=auth_headers).json()
    assert any(e["action"] == "shipment.created" for e in events)


def test_agent_creation_requires_admin(client, viewer_headers):
    res = client.post(
        "/api/agents",
        headers=viewer_headers,
        json={"name": "Naya", "kind": "dispatcher"},
    )
    assert res.status_code == 403


def test_duplicate_agent_name_is_409(client, auth_headers, seeded):
    res = client.post(
        "/api/agents",
        headers=auth_headers,
        json={"name": "Tarmeem", "kind": "dispatcher"},
    )
    assert res.status_code == 409


def test_exception_task_triages_incident(client, auth_headers, seeded):
    client.post(
        "/api/tasks",
        headers=auth_headers,
        json={
            "title": "Triage accident",
            "kind": "exception_handler",
            "shipment_id": seeded["shipment"].id,
            "payload": {"description": "Driver reports an accident near Sukkur"},
        },
    )
    body = client.post("/api/tasks/dispatch", headers=auth_headers).json()
    run = body["dispatched"][0]
    classify = next(s for s in run["steps"] if s["step"] == "classify")
    assert classify["detail"]["severity"] == "critical"


def test_inventory_auditor_reports_shortage(client, auth_headers, seeded):
    client.post(
        "/api/tasks",
        headers=auth_headers,
        json={
            "title": "Audit stock",
            "kind": "inventory_auditor",
            "payload": {
                "items": [
                    {"sku": "A-1", "on_hand": 5, "required": 10},
                    {"sku": "B-2", "on_hand": 20, "required": 20},
                ]
            },
        },
    )
    body = client.post("/api/tasks/dispatch", headers=auth_headers).json()
    run = body["dispatched"][0]
    compare = next(s for s in run["steps"] if s["step"] == "compare_stock")
    assert compare["detail"]["shortages"] == 1


def test_task_runs_endpoint_404s_for_unknown_task(client, auth_headers):
    assert client.get("/api/tasks/nope/runs", headers=auth_headers).status_code == 404


def test_security_headers_are_present(client):
    res = client.get("/api/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
