# API reference

Base URL: `http://127.0.0.1:8000`

All endpoints except `/api/health`, `/api/auth/register` and `/api/auth/login`
require `Authorization: Bearer <token>`.

Interactive docs are served at `/docs` (Swagger) and `/redoc`.

---

## Health

### `GET /api/health`

No auth. Returns:

```json
{"status": "ok", "app": "Qafila", "version": "1.0.0"}
```

---

## Auth

### `POST /api/auth/register`

Creates a `viewer`. There is no way to request a higher role.

```json
{"email": "new@example.com", "password": "at-least-8-chars"}
```

`201 Created`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "role": "viewer"
}
```

| Status | When |
|---|---|
| `409` | Email already registered |
| `422` | Password under 8 chars, over 72 bytes, or invalid email |

### `POST /api/auth/login`

```json
{"email": "operator@qafila.pk", "password": "qafila-demo-2026"}
```

`200 OK` — same shape as register.

`401` for both unknown email and wrong password, with the identical body:

```json
{"detail": "Incorrect email or password."}
```

That is intentional. Different messages would let an attacker enumerate accounts.

### `GET /api/auth/me`

`200 OK`

```json
{
  "id": "0d731aa28c6647c48110989371b569e6",
  "email": "operator@qafila.pk",
  "role": "admin",
  "created_at": "2026-11-01T18:58:12.441Z"
}
```

`401` if the token is missing, malformed, expired, or the user was deleted.

---

## Agents

### `GET /api/agents`

Any authenticated role. Sorted by name.

```json
[
  {
    "id": "a1b2c3...",
    "name": "Ginti",
    "kind": "inventory_auditor",
    "description": "Compares a manifest against stock on hand and raises shortages.",
    "max_concurrency": 2,
    "enabled": true,
    "created_at": "2026-11-01T18:58:12.441Z"
  }
]
```

`kind` is one of `dispatcher`, `route_optimizer`, `inventory_auditor`,
`exception_handler`.

### `POST /api/agents`

**Admin only.** `403` for operator and viewer.

```json
{
  "name": "Naya",
  "kind": "dispatcher",
  "description": "Optional, up to 2000 chars.",
  "max_concurrency": 2
}
```

`201 Created` · `409` if the name is taken · `422` if `max_concurrency` is
outside 1–16.

### `PATCH /api/agents/{agent_id}/toggle`

**Admin only.** Flips `enabled` and returns the agent. `404` if unknown.

A disabled agent is skipped at dispatch with an explicit reason, not silently
ignored.

---

## Shipments

### `GET /api/shipments`

Query params: `status` (optional filter), `limit` (1–500, default 100).

```json
[
  {
    "id": "0d731aa28c6647c48110989371b569e6",
    "reference": "QFL-1001",
    "origin_city": "Karachi",
    "destination_city": "Lahore",
    "weight_kg": 320.0,
    "distance_km": 1240.0,
    "status": "in_transit",
    "deadline_hours": 30.0,
    "created_at": "2026-11-01T18:58:12.441Z"
  }
]
```

`status` is one of `created`, `in_transit`, `delayed`, `delivered`, `cancelled`.

### `POST /api/shipments`

**Operator or admin.**

```json
{
  "reference": "QFL-1005",
  "origin_city": "Karachi",
  "destination_city": "Lahore",
  "weight_kg": 120,
  "distance_km": 1240,
  "deadline_hours": 48
}
```

`201 Created` · `409` duplicate reference · `403` viewer · `422` validation.

Validation bounds: `reference` 3–40 chars matching `^[A-Za-z0-9\-_]+$`,
`weight_kg` > 0 and ≤ 40,000, `distance_km` > 0 and ≤ 20,000,
`deadline_hours` > 0 and ≤ 720.

### `GET /api/shipments/{shipment_id}`

`200 OK` or `404`.

---

## Tasks

### `GET /api/tasks`

Query params: `status`, `limit` (1–500, default 100).

```json
[
  {
    "id": "029605582ffc489b8f09816819af9f43",
    "title": "Dispatch QFL-1001",
    "kind": "dispatcher",
    "status": "succeeded",
    "priority": 1,
    "payload": {"output": {"freight_pkr": 7543.82, "transit_hours": 26.8, "urgency": 0.893}},
    "shipment_id": "0d731aa28c6647c48110989371b569e6",
    "agent_id": "a1b2c3...",
    "depends_on_id": null,
    "created_at": "2026-11-01T19:02:11.102Z",
    "updated_at": "2026-11-01T19:02:11.204Z"
  }
]
```

`status` is one of `queued`, `running`, `succeeded`, `failed`, `blocked`,
`cancelled`.

### `POST /api/tasks`

**Operator or admin.**

```json
{
  "title": "Optimise route QFL-1001",
  "kind": "route_optimizer",
  "priority": 2,
  "shipment_id": "0d731aa28c6647c48110989371b569e6",
  "depends_on_id": "029605582ffc489b8f09816819af9f43",
  "payload": {}
}
```

`201 Created` · `422` if `shipment_id` or `depends_on_id` does not exist.

`priority` is 1–10, where 1 runs first.

### `POST /api/tasks/dispatch`

**Operator or admin.** Query param `max_tasks` (1–50, default 10).

Drains the runnable queue. Returns what ran and what did not, with reasons.

```json
{
  "dispatched": [
    {
      "id": "run-id",
      "task_id": "029605582ffc489b8f09816819af9f43",
      "agent_id": "a1b2c3...",
      "status": "succeeded",
      "steps": [
        {"step": "load_shipment", "at": "2026-11-01T19:02:11.150Z", "detail": {"shipment_id": "0d73..."}},
        {"step": "compute_plan", "at": "2026-11-01T19:02:11.180Z",
         "detail": {"freight_pkr": 7543.82, "transit_hours": 26.8, "slack_hours": 3.2, "urgency": 0.893}},
        {"step": "assign_carrier", "at": "2026-11-01T19:02:11.204Z", "detail": {"status": "in_transit"}}
      ],
      "tokens_used": 540,
      "cost_usd": 0.00108,
      "error": null,
      "started_at": "2026-11-01T19:02:11.102Z",
      "finished_at": "2026-11-01T19:02:11.204Z"
    }
  ],
  "skipped": [
    {"task_id": "child-task-id", "reason": "Dependency is queued, not succeeded."}
  ],
  "message": "Dispatched 1 task(s); 1 left in the queue."
}
```

Skip reasons you will actually see:

- `Dependency is queued, not succeeded.`
- `Dependency is failed, not succeeded.`
- `Dependency task no longer exists.`
- `All 'dispatcher' agents are at capacity: Tarmeem (3/3).`
- `All 'dispatcher' agents are disabled: Tarmeem.`
- `No agent registered for kind 'route_optimizer'.`

### `GET /api/tasks/{task_id}/runs`

All runs for a task, newest first. `404` if the task does not exist.

### `GET /api/runs`

Query param `limit` (1–200, default 50). Same run shape as above.

---

## Observability

### `GET /api/metrics`

Any authenticated role.

```json
{
  "tasks_by_status": {
    "queued": 0, "running": 0, "succeeded": 2,
    "failed": 0, "blocked": 0, "cancelled": 0
  },
  "runs_total": 2,
  "runs_failed": 0,
  "tokens_used": 1080,
  "cost_usd": 0.00216,
  "agents_busy": {},
  "shipments_by_status": {
    "created": 3, "in_transit": 1, "delayed": 0,
    "delivered": 0, "cancelled": 0
  }
}
```

Every status key is present even at zero, so a dashboard does not have to
handle missing keys.

### `GET /api/audit`

**Admin only.** `403` otherwise. Query param `limit` (1–500, default 100).

```json
[
  {
    "id": "evt-id",
    "actor_id": "0d731aa28c6647c48110989371b569e6",
    "action": "shipment.created",
    "entity_type": "shipment",
    "entity_id": "0d731aa28c6647c48110989371b569e6",
    "detail": {"reference": "QFL-1001"},
    "created_at": "2026-11-01T18:58:12.441Z"
  }
]
```

Actions recorded: `user.registered`, `agent.created`, `agent.toggled`,
`shipment.created`, `task.created`, `tasks.dispatched`.

---

## Error format

Every error is `{"detail": "..."}`. Validation errors from Pydantic use
FastAPI's standard list form:

```json
{
  "detail": [
    {
      "type": "greater_than",
      "loc": ["body", "weight_kg"],
      "msg": "Input should be greater than 0",
      "input": -5
    }
  ]
}
```

Engine-level `ValueError`s are caught by a handler and returned as `422` with a
plain string `detail`, so a bad payload never surfaces as a 500.

## Rate limiting

240 requests per minute per client IP, per process. Exceeding it returns `429`
with a `Retry-After` header.

**Limitation:** the counter is in-process. Running N uvicorn workers allows N
times the configured rate. See [usage.md](usage.md#known-limitations).
