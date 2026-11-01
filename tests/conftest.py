"""Test fixtures: an isolated in-memory database per test."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SEED_DEMO_DATA", "false")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Agent, AgentKind, Role, Shipment, User  # noqa: E402
from app.security import hash_password  # noqa: E402


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db_session) -> User:
    user = User(
        email="admin@test.pk",
        password_hash=hash_password("test-password-123"),
        role=Role.admin,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def viewer_user(db_session) -> User:
    user = User(
        email="viewer@test.pk",
        password_hash=hash_password("test-password-123"),
        role=Role.viewer,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(client, admin_user) -> dict:
    res = client.post(
        "/api/auth/login",
        json={"email": "admin@test.pk", "password": "test-password-123"},
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def viewer_headers(client, viewer_user) -> dict:
    res = client.post(
        "/api/auth/login",
        json={"email": "viewer@test.pk", "password": "test-password-123"},
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def seeded(db_session):
    """One agent of each kind plus a shipment, for dispatch tests."""
    agents = [
        Agent(name="Tarmeem", kind=AgentKind.dispatcher, max_concurrency=2),
        Agent(name="Raasta", kind=AgentKind.route_optimizer, max_concurrency=1),
        Agent(name="Ginti", kind=AgentKind.inventory_auditor, max_concurrency=1),
        Agent(name="Nigraan", kind=AgentKind.exception_handler, max_concurrency=2),
    ]
    shipment = Shipment(
        reference="QFL-TEST-1",
        origin_city="Karachi",
        destination_city="Lahore",
        weight_kg=320.0,
        distance_km=1240.0,
        deadline_hours=30.0,
    )
    db_session.add_all([*agents, shipment])
    db_session.commit()
    for agent in agents:
        db_session.refresh(agent)
    db_session.refresh(shipment)
    return {"agents": agents, "shipment": shipment}
