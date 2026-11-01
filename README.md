# Qafila (قافلہ) — Logistics AI Agent Platform

> A caravan of AI agents that runs your supply chain — dispatch, routing, inventory and demand forecasting, orchestrated from one dashboard.

**Day 7 of the Autonomous AI Software Engineer — 30 Day Challenge.**

Qafila is an AWS-AI-Agents-style platform for logistics and supply chains. Instead of one monolithic system, you get a team of small, focused AI agents — a **Dispatcher** that assigns shipments to the cheapest vehicle that fits, a **Route Planner** that computes ETAs and costs, a **Stock Keeper** that flags low inventory, and a **Demand Forecaster** that predicts what to reorder. You queue tasks, hit "Run queue", and watch each agent do its job with a full audit trail.

## Why this exists

Small logistics companies in Pakistan run on WhatsApp and gut feeling. A dispatcher juggles ten phone calls to find a van; the warehouse only notices a stockout when a customer asks; nobody knows what demand looks like next week. Qafila gives a small operator the same kind of agent orchestration that big cloud platforms sell to enterprises — without the enterprise price tag.

## Features

- **Four AI agents** — dispatch, route, inventory, demand — each a deterministic, testable engine
- **Task orchestration** — queue tasks, run the queue, see every input and output
- **Auto-dispatch** — create a shipment and the dispatcher assigns the cheapest available vehicle that fits the load, with ETA and cost
- **Shipment lifecycle** — created → assigned → in transit → delivered, with vehicles freed on delivery
- **Fleet management** — bikes, vans and trucks with capacity and cost-per-km
- **Audit trail** — every agent action and shipment milestone logged as an event
- **JWT auth** with bcrypt password hashing, per-user data isolation
- **Rate limiting**, security headers, input validation on every endpoint
- **Mobile-first SPA** — no build step, vanilla JS, works on a phone
- **SQLite by default, PostgreSQL-ready** via `DATABASE_URL`

## Screenshots

| Dashboard | Shipments |
|---|---|
| ![Dashboard](screenshots/dashboard.jpg) | ![Shipments](screenshots/shipments.jpg) |

| Task board | Agents |
|---|---|
| ![Tasks](screenshots/tasks.jpg) | ![Agents](screenshots/agents.jpg) |

| Login | Mobile |
|---|---|
| ![Login](screenshots/login.jpg) | ![Mobile](screenshots/mobile.jpg) |

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11 · FastAPI · SQLAlchemy 2.0 · Pydantic v2 |
| Auth | JWT (HS256) · bcrypt |
| Frontend | Vanilla JS SPA · CSS grid · Inter font |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Tooling | pytest · ruff · black · Docker |

## Quick start

```bash
git clone https://github.com/mohdabrarbaloch-arch/day-7-qafila.git
cd day-7-qafila
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open http://localhost:8000 and sign in with the demo account:

```
demo@qafila.pk / demo12345
```

Or with Docker:

```bash
docker compose up --build
```

## Try it in 60 seconds

1. Sign in with the demo account.
2. Go to **Fleet** — three vehicles are already there (bike, van, truck).
3. Go to **Shipments** → **New shipment** → `Karachi → Lahore`, 100 kg.
4. Watch the dispatcher assign the van and quote PKR 48,400 with a 20.2h ETA.
5. Go to **Tasks** → queue a route task with a stopover, hit **Run queue**, and read the agent's output.

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Get JWT |
| GET | `/api/auth/me` | Current user |
| GET/POST | `/api/agents` | List / create agents |
| PATCH/DELETE | `/api/agents/{id}` | Update / delete agent |
| GET/POST | `/api/tasks` | List / queue tasks |
| POST | `/api/tasks/run` | Execute the queue |
| GET/POST | `/api/fleet` | List / add vehicles |
| GET/POST | `/api/shipments` | List / create shipments (auto-dispatch) |
| POST | `/api/shipments/{id}/advance` | Advance lifecycle |
| GET | `/api/dashboard` | Aggregated stats + events |

Full reference in [docs/api.md](docs/api.md).

## Tests

```bash
pytest              # 43 tests
ruff check .        # lint
black --check .     # format
```

## Project structure

```
app/
  core/        config, database, security
  engine/      logistics agent logic + task runner
  routers/     auth, agents, tasks, fleet, shipments, dashboard
  static/      SPA (index.html, css, js)
  main.py      FastAPI entrypoint
tests/         engine + API tests
docs/          setup, usage, API reference
```

## License

MIT — see [LICENSE](LICENSE).

---

*Built in one day as part of the 30 Day Challenge. No placeholders, no fake data — every agent output is computed, not canned.*
