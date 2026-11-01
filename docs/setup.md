# Setup

## Requirements

- Python 3.11 or newer
- Docker (optional, for the Postgres path)

## Local install

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

`requirements-dev.txt` pulls in the runtime deps plus pytest, ruff and black.

## Configuration

Copy the example file and edit as needed:

```bash
cp .env.example .env
```

Every variable has a working default, so you can skip this entirely for local
work. The one you must set before production is `JWT_SECRET`.

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | Set to `production` to enable the secret check |
| `DATABASE_URL` | `sqlite:///./qafila.db` | Postgres URL works unchanged |
| `JWT_SECRET` | dev placeholder | **Must** be changed in production |
| `ACCESS_TOKEN_MINUTES` | `1440` | 24 hours |
| `CORS_ORIGINS` | `*` | Comma-separated list in production |
| `RATE_LIMIT_PER_MINUTE` | `240` | Per client IP, per process |
| `SEED_DEMO_DATA` | `true` | Set `false` for a clean database |
| `DEMO_EMAIL` | `operator@qafila.pk` | Demo account address |
| `DEMO_PASSWORD` | `qafila-demo-2026` | Empty in production = no demo account |

If `ENVIRONMENT=production` and `JWT_SECRET` is still the development default,
the app refuses to start. That is deliberate — a known secret in production is
worse than a crash.

## Run it

```bash
uvicorn app.main:app --reload
```

- App: <http://127.0.0.1:8000>
- Interactive API docs: <http://127.0.0.1:8000/docs>

On first boot the database is created and seeded with four agents, four
shipments and a demo admin account.

## Demo credentials

```
operator@qafila.pk / qafila-demo-2026
```

This account has the `admin` role so the audit log is visible. It is created
only outside production: with `ENVIRONMENT=production` the seed uses
`DEMO_PASSWORD` and nothing else, so a deployed instance has no known login
unless you deliberately set one. Delete it or change the password before any
real use.

## Creating a real admin

Self-registration always produces a `viewer`. To promote someone, do it in the
database rather than through an API call:

```bash
python - <<'PY'
from app.database import SessionLocal
from app.models import User, Role
db = SessionLocal()
user = db.query(User).filter(User.email == "you@example.com").one()
user.role = Role.admin
db.commit()
print(f"{user.email} is now {user.role.value}")
PY
```

There is no endpoint for this on purpose. A privilege escalation path reachable
over HTTP is a privilege escalation path an attacker can reach too.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Brings up Postgres 16 and the app. The app waits for the database healthcheck
before starting.

To run only the database and keep the app on your host:

```bash
docker compose up -d db
export DATABASE_URL=postgresql+psycopg://qafila:qafila@localhost:5432/qafila
uvicorn app.main:app --reload
```

## Deploying to Vercel

The repo includes `vercel.json` with the Python runtime configured. Once you
have a token:

```bash
npm i -g vercel
vercel --prod --yes --token "$VERCEL_TOKEN"
```

Two things to set in the Vercel dashboard before the first deploy:

1. `JWT_SECRET` — a real random value (`openssl rand -hex 32`)
2. `DATABASE_URL` — a hosted Postgres URL. SQLite will not persist on
   serverless; the filesystem is read-only and ephemeral.

**Honest note:** this project was not deployed during development because no
Vercel token was available in the build environment. The config is present and
the production build passes locally, but the deploy itself is unverified.

## Running the checks

```bash
pytest -q
ruff check .
black --check .
```

All three pass on a clean checkout. If `black --check` fails after you edit
something, run `black .` — the project is formatted at line length 100.

## Troubleshooting

**`RuntimeError: JWT_SECRET is still the development default`**
You set `ENVIRONMENT=production` without a real secret. Set `JWT_SECRET`.

**`sqlite3.OperationalError: database is locked`**
Two processes are writing to the same SQLite file. Use Postgres, or run a
single worker.

**Login returns 401 with the demo credentials**
The database was seeded before you changed `SEED_DEMO_DATA`, or you are pointing
at a different `DATABASE_URL`. Delete `qafila.db` and restart.

**`ModuleNotFoundError: No module named 'app'`**
Run uvicorn from the project root, not from inside `app/`.
