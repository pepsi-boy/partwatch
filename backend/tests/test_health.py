from fastapi.testclient import TestClient

from app.api import health
from app.main import app

client = TestClient(app)


def test_health_ok_when_dependencies_up(monkeypatch):
    monkeypatch.setattr(health, "check_database", lambda: True)
    monkeypatch.setattr(health, "check_redis", lambda: True)

    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


def test_health_503_when_redis_down(monkeypatch):
    monkeypatch.setattr(health, "check_database", lambda: True)
    monkeypatch.setattr(health, "check_redis", lambda: False)

    resp = client.get("/health")

    assert resp.status_code == 503
    assert resp.json()["status"] == "degraded"
    assert resp.json()["checks"]["redis"] == "down"


def test_health_against_real_services():
    """Runs against the real Postgres and Redis from docker compose / CI."""
    resp = client.get("/health")
    assert resp.status_code == 200, resp.json()
