from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.api import admin, deals, health, parts, status
from app.logging_config import configure_logging

configure_logging()

app = FastAPI(
    title="PartWatch API",
    version="0.1.0",
    description=(
        "Tracks Best Buy prices for PC parts, keeps price history, and detects deals. "
        "Write routes need `Authorization: Bearer <ADMIN_TOKEN>` (use the Authorize button)."
    ),
)
app.include_router(health.router, tags=["health"])
app.include_router(parts.router)
app.include_router(deals.router)
app.include_router(status.router)
app.include_router(admin.router)

DASHBOARD = (Path(__file__).parent / "static" / "index.html").read_text()


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> str:
    return DASHBOARD
