# Architecture — Qafila

Qafila is a control plane for logistics agents. The point is not that agents
exist; it is that every decision an agent makes is **readable, priced, and
replayable**. A dispatcher who cannot explain why a shipment was flagged is a
dispatcher nobody trusts.

## System diagram

```
                        ┌──────────────────────────────┐
                        │   Browser (vanilla JS SPA)   │
                        │  Queue · Shipments · Agents  │
                        └──────────────┬───────────────┘
                                       │  JSON over HTTPS
                                       │  Bearer JWT
                        ┌──────────────▼───────────────┐
                        │        FastAPI app           │
                        │  ┌────────────────────────┐  │
                        │  │ middleware             │  │
                        │  │  CORS · security hdrs  │  │
                        │  │  rate limit (in-proc)  │  │
                        │  └───────────┬────────────┘  │
                        │  ┌───────────▼────────────┐  │
                        │  │ routers                │  │
                        │  │  auth · registry       │  │
                        │  │  tasks · observability │  │
                        │  └───────────┬────────────┘  │
                        │  ┌───────────▼────────────┐  │
                        │  │ engine (pure logic)    │  │
                        │  │  routing · triage      │  │
                        │  │  dispatch · executor   │  │
                        │  └───────────┬────────────┘  │
                        └──────────────┼───────────────┘
                                       │ SQLAlchemy 2.0
                        ┌──────────────▼───────────────┐
                        │  SQLite (dev) / Postgres 16  │
                        │  users · agents · shipments  │
                        │  tasks · runs · audit_events │
                        └──────────────────────────────┘
```

## Layers, and why they are split this way

**`app/engine/` is pure.** No database session, no HTTP, no clock reads except
where a timestamp is explicitly passed in. `routing.py`, `triage.py` and
`dispatch.py` take plain values and return plain values. That is what makes 74
tests run in under two seconds and what lets a finance analyst check the cost
model without reading a router.

**`app/routers/` owns HTTP.** Status codes, role gates, and turning engine
`ValueError`s into 422s. Routers do not contain business arithmetic.

**`app/engine/executor.py` is the only place that writes a `Run`.** It is the
error boundary: any exception inside a handler becomes a failed run with the
traceback message stored, not a 500 to the caller. A dispatch of ten tasks
where one fails still returns nine successes.

## Data model

```
User ──owns──> Task ──has many──> Run
                │                  │
                ├──> Shipment      └── steps (JSON array)
                ├──> Agent
                └──> Task (depends_on_id, self-referential)

AuditEvent — append-only, references any entity by (type, id)
```

`Task.depends_on_id` makes the queue a DAG rather than a flat list. A task is
runnable only when its dependency is `succeeded` — not `running`, not `failed`.
That distinction is enforced in `dispatch.is_runnable()` and covered by tests,
because "the parent is still going" and "the parent died" need different
responses from an operator.

`Run.steps` is a JSON array of `{step, at, detail}`. Storing the trace on the
run rather than in a separate table keeps the read path to one query, which is
the right trade at this scale. If traces grow past a few hundred steps, move
them to their own table and keep a summary on the run.

## Data flow: one dispatch

1. `POST /api/tasks/dispatch` loads every `queued` task.
2. Each task's dependency status is resolved into a `QueueItem`.
3. `order_queue()` filters to runnable items and sorts by priority, then age.
4. For each item, `select_agent()` picks the least-loaded eligible agent of the
   matching kind. Capacity is re-checked against in-batch load, so two tasks in
   one batch cannot both take the last slot.
5. `execute_task()` runs the handler, writes the step trace, and sets the task
   to `succeeded` or `failed`.
6. Anything not run gets an explicit `skipped` reason — "all agents at
   capacity", "dependency is queued, not succeeded". Silence is not an option
   here; an operator needs to know why their task did not move.

## Cost model

Freight cost is deterministic and documented so it can be argued with:

```
cost = BASE_FEE + (PER_KM_PER_KG × distance × weight × tier) × (1 + fuel)
```

- `BASE_FEE` = 250 PKR
- `PER_KM_PER_KG` = 0.018
- `fuel` = 11%
- `tier` steps down at 50 / 500 / 5000 kg (1.00 / 0.92 / 0.84 / 0.78)

Transit time uses distance-banded average speeds (22 / 45 / 58 / 52 km/h) plus
3 hours of handling. Long hauls average faster than city runs because they are
motorway-dominated; that is a modelling choice, stated rather than hidden.

## Scaling notes

**What is already right.** Stateless app process, all state in the database,
engine logic pure and parallelisable, `Run` rows shaped for a worker queue.

**What breaks first, in order:**

1. **Rate limiting is per-process.** N uvicorn workers allow N× the configured
   rate. Move to Redis with a sliding window before running more than one
   worker behind real traffic.
2. **Dispatch is synchronous.** A slow handler blocks the request. The fix is
   to have `execute_task` enqueue to a worker (Celery/RQ/arq) and return the
   `Run` in `running` state; the data model already supports this without
   migration.
3. **SQLite write contention.** Fine for a demo, not for concurrent dispatch.
   Postgres via `docker-compose` is the intended production path.
4. **No pagination cursors.** `limit` only. Add keyset pagination on
   `created_at` before the tables get large.

**What I would not change.** The pure engine. Keeping arithmetic out of the
request path is what makes this testable, and testability is the whole product
claim.

## Security posture

- bcrypt at cost 12, with a hard 72-byte rejection rather than silent truncation
- JWT HS256, 24h expiry, secret from env only; production refuses to boot on
  the development default
- Self-registration always yields `viewer`; admin is granted out of band
- Login returns an identical message for unknown-user and wrong-password
- Role gates: `viewer` reads, `operator` writes, `admin` manages agents and
  reads the audit log
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`

**Known gaps, stated plainly:** no Content-Security-Policy (the SPA uses inline
event handlers, so adding one requires refactoring `app.js` first), no
refresh-token rotation, no account lockout after repeated failures, and the
rate limiter is in-process as noted above.
