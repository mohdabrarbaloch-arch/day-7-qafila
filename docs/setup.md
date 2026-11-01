# Setup

## Prerequisites

- Python 3.11+
- (Optional) Docker + Docker Compose

## Local development

```bash
git clone https://github.com/mohdabrarbaloch-arch/day-7-qafila.git
cd day-7-qafila
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

The app is served at http://localhost:8000. The API docs are at http://localhost:8000/docs.

## Demo account

On first boot the app seeds a demo operator:

```
demo@qafila.pk / demo12345
```

and an admin:

```
admin@qafila.pk / admin12345
```

The demo account comes with four agents (dispatch, route, inventory, demand) and three vehicles (bike, van, truck) so you can try the whole flow immediately.

## Docker

```bash
docker compose up --build
```

## PostgreSQL

Set `DATABASE_URL` to a PostgreSQL connection string:

```
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/qafila
```

Tables are created automatically on startup.

## Environment variables

See [.env.example](../.env.example) for the full list with comments. The only one you must change in production is `SECRET_KEY`.
