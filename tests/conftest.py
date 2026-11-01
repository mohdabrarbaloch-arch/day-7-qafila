"""Shared fixtures — in-memory SQLite, seeded app, test client."""

import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["RATE_LIMIT_PER_MINUTE"] = "10000"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def auth_headers(client):
    r = client.post(
        "/api/auth/register",
        json={"email": "tester@qafila.pk", "name": "Tester", "password": "secret123"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def demo_agent(client, auth_headers):
    r = client.post(
        "/api/agents",
        headers=auth_headers,
        json={"name": "Dispatcher", "kind": "dispatch", "description": "Test dispatcher"},
    )
    assert r.status_code == 201, r.text
    return r.json()
