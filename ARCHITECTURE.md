# Qafila — Architecture

## System overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser (SPA)                        │
│   Dashboard · Agents · Tasks · Shipments · Fleet            │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST + JWT (Bearer)
┌──────────────────────────▼──────────────────────────────────┐
│                     FastAPI application                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │  auth    │  │  agents  │  │  tasks   │  │  shipments  │  │
│  │  router  │  │  router  │  │  router  │  │   router    │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬──────┘  │
│       │             │             │               │         │
│  ┌────▼─────────────▼─────────────▼───────────────▼──────┐  │
│  │              Engine (pure, deterministic)             │  │
│  │  dispatch · route · inventory · demand  +  runner     │  │
│  └──────────────────────────┬────────────────────────────┘  │
│                            │ SQLAlchemy ORM                 │
│  ┌─────────────────────────▼──────────────────────────────┐ │
│  │   SQLite (dev) / PostgreSQL (prod)                     │ │
│  │   users · agents · tasks · shipments · vehicles ·      │ │
│  │   events                                               │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Data flow

1. **Auth** — user registers/logs in; server hashes the password with bcrypt (12 rounds) and issues a JWT (HS256, 24h expiry). Every subsequent request carries the token; `deps.get_current_user` decodes it and loads the user.
2. **Agents** — a user creates agents of four kinds. Each kind maps to a pure function in `app/engine/logistics.py` that takes `(input_data, context)` and returns a result dict. No I/O inside the functions — that's what makes them unit-testable.
3. **Tasks** — the user queues a task against an agent with JSON input. `POST /api/tasks/run` invokes the runner, which executes queued tasks oldest-first, records `started_at`/`finished_at`, stores the output (or the error), and writes an audit event.
4. **Shipments** — creating a shipment triggers the dispatch agent synchronously: it picks the cheapest available vehicle whose capacity fits the weight, computes distance from the road-distance table, sets ETA (distance / 60 km/h) and cost (distance × cost-per-km), marks the vehicle `on_route`, and logs an event. `advance` moves the shipment through its lifecycle and frees the vehicle on delivery.
5. **Dashboard** — aggregates counts across the user's own rows and returns the 10 most recent events.

## Agent context

Agents receive a read-only `AgentContext` (fleet snapshot, recent shipments, inventory levels, demand history). This keeps the engine decoupled from the database — the runner builds the context from ORM rows, and tests build it from plain dicts.

## Distance model

A curated table of inter-city road distances for the demo network (Karachi, Lahore, Islamabad, Peshawar, Quetta, Faisalabad, Multan, Hyderabad, Sukkur) with city-alias normalization. Unknown pairs fall back to a deterministic pseudo-distance so results are reproducible.

## Security

- Passwords: bcrypt, 12 rounds, never stored in plaintext
- Tokens: JWT HS256 with 24h expiry; `sub` is the user id
- Rate limiting: slowapi, 120 req/min per IP by default
- Headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`
- CORS: configurable origins via `CORS_ORIGINS`
- Secrets: only via environment / `.env` — nothing hardcoded
- Ownership: every query is scoped by `owner_id`; cross-user access returns 404

## Scaling notes

- **Stateless API** — the app holds no in-memory per-user state, so it scales horizontally behind a load balancer.
- **Database** — swap `DATABASE_URL` to PostgreSQL for production; the ORM layer is identical. Add indexes on `owner_id` columns (already indexed) and consider partitioning `events` by time at scale.
- **Task queue** — the synchronous runner is fine for a small operator. For high volume, move task execution to a background worker (Celery/ARQ) and keep the API for enqueueing; the engine functions are already pure and portable.
- **Distance data** — replace the static table with a routing API (OSRM/Google) behind the same `road_distance_km` interface.
- **Frontend** — the SPA is static; serve it from a CDN and keep the API on its own domain when scaling.
