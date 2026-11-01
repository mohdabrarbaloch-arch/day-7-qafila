"""Qafila — Logistics AI Agent Platform. FastAPI application entrypoint."""

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.engine.logistics import AGENT_DESCRIPTIONS
from app.models import Agent, User, Vehicle
from app.routers import agents, auth, dashboard, fleet, shipments, tasks

settings = get_settings()

limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.rate_limit_per_minute}/minute"])

STATIC_DIR = Path(__file__).parent / "static"


def seed_demo_data() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return
        admin = User(
            email="admin@qafila.pk",
            name="Qafila Admin",
            hashed_password=hash_password("admin12345"),
            role="admin",
        )
        db.add(admin)
        db.flush()

        demo = User(
            email="demo@qafila.pk",
            name="Demo Operator",
            hashed_password=hash_password("demo12345"),
            role="operator",
        )
        db.add(demo)
        db.flush()

        for kind, name in (
            ("dispatch", "Dispatcher"),
            ("route", "Route Planner"),
            ("inventory", "Stock Keeper"),
            ("demand", "Demand Forecaster"),
        ):
            db.add(Agent(owner_id=demo.id, name=name, kind=kind, description=AGENT_DESCRIPTIONS[kind]))

        for v in (
            ("Bike-01", "bike", 50.0, 15.0),
            ("Van-01", "van", 800.0, 40.0),
            ("Truck-01", "truck", 5000.0, 90.0),
        ):
            db.add(Vehicle(owner_id=demo.id, name=v[0], vehicle_type=v[1], capacity_kg=v[2], cost_per_km=v[3]))
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        seed_demo_data()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "AI agent orchestration for logistics and supply chains " "— dispatch, routing, inventory and demand agents."
    ),
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.middleware("http")
async def add_process_time(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - start) * 1000:.1f}"
    return response


app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(agents.router, prefix=settings.api_prefix)
app.include_router(tasks.router, prefix=settings.api_prefix)
app.include_router(fleet.router, prefix=settings.api_prefix)
app.include_router(shipments.router, prefix=settings.api_prefix)
app.include_router(dashboard.router, prefix=settings.api_prefix)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
