# API Reference

Base URL: `/api`. All endpoints except `auth/register`, `auth/login` and `health` require a Bearer token.

## Auth

### POST /auth/register
Create an account. Returns a token and the user.

```json
{"email": "you@company.pk", "name": "Ayesha Khan", "password": "secret123"}
```

- `201` — created
- `409` — email already registered
- `422` — validation error (password must be ≥8 chars with letters and digits)

### POST /auth/login
```json
{"email": "you@company.pk", "password": "secret123"}
```
- `200` — `{access_token, token_type, user}`
- `401` — invalid credentials

### GET /auth/me
Returns the current user. `401` without a token.

## Agents

### GET /agents
List the current user's agents.

### POST /agents
```json
{"name": "Dispatcher", "kind": "dispatch", "description": "optional", "config": {}}
```
`kind` must be one of `dispatch | route | inventory | demand`. `201` on success, `422` otherwise.

### GET /agents/kinds
Returns the four agent kinds with descriptions.

### GET /agents/{id} · PATCH /agents/{id} · DELETE /agents/{id}
Update accepts `name`, `description`, `status` (`idle|running|paused`), `config`. `404` if not found or not owned.

## Tasks

### GET /tasks
List the user's tasks, newest first (max 100).

### POST /tasks
```json
{"agent_id": 1, "title": "Dispatch to Lahore", "input_data": {"weight_kg": 100, "origin": "Karachi", "destination": "Lahore"}}
```
`404` if the agent doesn't exist or isn't yours.

### POST /tasks/run
Executes queued tasks oldest-first. Returns `{"ran": N}`.

### GET /tasks/{id}
`404` if not found or not owned.

## Fleet

### GET /fleet · POST /fleet
```json
{"name": "Van-02", "vehicle_type": "van", "capacity_kg": 800, "cost_per_km": 40}
```
`vehicle_type` must be `bike | van | truck`. `201` on success.

### PATCH /fleet/{id}
Accepts `status` (`available|on_route|maintenance`) and `location`.

### DELETE /fleet/{id}
`204` on success.

## Shipments

### GET /shipments · POST /shipments
```json
{"origin": "Karachi", "destination": "Lahore", "weight_kg": 100}
```
Creating a shipment runs the dispatch agent: on success the response has `status: "assigned"`, a `vehicle_id`, `eta_hours` and `cost`. If no vehicle fits, `status` stays `created`.

### GET /shipments/{id}
`404` if not found or not owned.

### POST /shipments/{id}/advance
Moves `created → assigned → in_transit → delivered`. `400` if already delivered. Frees the vehicle on delivery.

## Dashboard

### GET /dashboard
```json
{
  "shipments_total": 3, "shipments_in_transit": 1, "shipments_delivered": 1,
  "agents_total": 4, "agents_running": 0,
  "tasks_queued": 2, "tasks_done": 5,
  "fleet_available": 2, "fleet_on_route": 1,
  "recent_events": [{"id": 1, "kind": "dispatch", "message": "...", "created_at": "..."}]
}
```

## Health

### GET /health
`{"status": "ok", "app": "...", "version": "1.0.0"}`

## Errors

All errors return JSON: `{"detail": "message"}`. Status codes: `400` bad request, `401` unauthenticated, `403` forbidden, `404` not found, `409` conflict, `422` validation, `429` rate limited.
