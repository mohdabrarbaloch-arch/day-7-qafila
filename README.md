# Qafila — قافلہ

**A control plane for logistics agents.** Dispatch freight, rank routes, audit
stock and triage incidents — with every decision priced and every step traceable.

[![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/tests-74%20passing-brightgreen)](#tests)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## Why this exists

Most "AI agent" dashboards show you a chat log and call it observability. That
is useless when a shipment is late and someone asks *why*.

Qafila takes the opposite position: an agent's decision should be a number you
can check by hand. Every run stores its steps, its token count and its cost.
Every freight quote comes from a formula printed in the docs. If the agent says
a shipment will miss its deadline, you can divide distance by speed and confirm
it yourself.

The four agents are deliberately rule-based rather than LLM-backed. A dispatcher
needs to argue with the logic, and a keyword table is something you can read,
disagree with, and change in a pull request.

## What it does

**Dispatch** — prices a shipment, computes transit time, and flags it as at-risk
when the deadline is physically impossible. At-risk shipments move to `delayed`
automatically.

**Route optimisation** — ranks candidate routes on freight cost, tolls and a
stated risk penalty, then explains the pick. A longer motorway detour can beat a
shorter direct road when the risk difference is large enough.

**Inventory audit** — compares a manifest against stock on hand and raises
per-SKU shortages.

**Exception triage** — turns a free-text incident into a severity and a next
action. "Accident" escalates to a human; "delayed due to traffic" notifies the
customer. High-value cargo raises the severity floor, because a delay on a
2M PKR shipment is not the same event as a delay on a 5k one.

**Orchestration** — tasks form a DAG. A child task will not run until its parent
has *succeeded* — not merely started. Agents have concurrency limits enforced at
dispatch, and anything that cannot run gets an explicit reason instead of
silently sitting in the queue.

## Screenshots

| Dashboard | Shipments |
|---|---|
| ![Dashboard](screenshots/02-dashboard.png) | ![Shipments](screenshots/03-shipments.png) |

| Agents | Mobile |
|---|---|
| ![Agents](screenshots/04-agents.png) | ![Mobile](screenshots/05-mobile.png) |

## Live demo

**Not deployed.** There is no Vercel token in the build environment, so rather
than paste a URL that 404s, here is the honest state: the app runs locally, the
production build passes, and `vercel.json` is ready. Deployment steps are in
[docs/setup.md](docs/setup.md#deploying-to-vercel) and take about two minutes
once a token is available.

## Quick start

```bash
git clone https://github.com/mohdabrarbaloch-arch/day-7-qafila.git
cd day-7-qafila

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. The database is created and seeded on first boot.

**Demo login:** `operator@qafila.pk` / `qafila-demo-2026`

That account is an admin so you can see the audit log. It is created only in
development — with `ENVIRONMENT=production` the seed requires an explicit
`DEMO_PASSWORD`, so a deployed instance never comes up with a known login.

### With Docker

```bash
cp .env.example .env
docker compose up --build
```

This brings up Postgres 16 and the app on port 8000.

## Tests

```bash
pytest -q          # 74 passed
ruff check .       # All checks passed
black --check .    # 26 files unchanged
```

The suite covers the cost model against hand-computed values, every triage rule
including the ordering that makes it work, agent selection under capacity
pressure, DAG gating, role enforcement, and the full dispatch path through the
API.

## Project layout

```
app/
  engine/          pure logic — no DB, no HTTP
    routing.py     freight cost, transit time, route ranking
    triage.py      incident classification rules
    dispatch.py    agent selection, queue ordering, DAG gating
    executor.py    runs a task, records the step trace
  routers/         HTTP layer
  models.py        SQLAlchemy 2.0 models
  schemas.py       Pydantic validation (single source of truth)
  security.py      bcrypt + JWT
  static/          the SPA — no build step
tests/             74 tests
docs/              setup, usage, API reference
```

## Tech stack

Python 3.11 · FastAPI 0.115 · SQLAlchemy 2.0 · Pydantic v2 · bcrypt · PyJWT ·
SQLite (dev) / PostgreSQL 16 (prod) · vanilla JS SPA · Docker

## Documentation

- [Setup](docs/setup.md) — install, configure, deploy
- [Usage](docs/usage.md) — the cost model, triage rules, and how to read a trace
- [API reference](docs/api.md) — every endpoint with real request/response bodies

## License

MIT — see [LICENSE](LICENSE).
