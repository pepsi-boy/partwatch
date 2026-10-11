from fastapi import APIRouter, Response, status
from redis import Redis
from sqlalchemy import text

from app.config import get_settings
from app.db import engine

router = APIRouter()


def check_database() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def check_redis() -> bool:
    try:
        client = Redis.from_url(get_settings().redis_url, socket_timeout=2)
        return bool(client.ping())
    except Exception:
        return False


@router.get("/health")
def health(response: Response) -> dict:
    checks = {"database": check_database(), "redis": check_redis()}
    healthy = all(checks.values())
    # 503 lets Render (or any load balancer) see that the service is degraded.
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if healthy else "degraded",
        "checks": {name: "ok" if ok else "down" for name, ok in checks.items()},
    }
