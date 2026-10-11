from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Deal, JobRun, Part, PriceSnapshot
from app.schemas import JobRunOut, StatusOut
from app.services.alerts import get_sender
from app.services.providers import is_demo_mode

router = APIRouter(tags=["status"])

# A run still "running" after this long lost tasks (e.g. a worker restart wiped the
# in-memory queue). Shown as "stale" so it doesn't look healthy forever.
STALE_AFTER = timedelta(hours=1)


def run_out(run: JobRun, now: datetime) -> JobRunOut:
    out = JobRunOut.model_validate(run)
    if run.finished_at:
        out.duration_seconds = round((run.finished_at - run.started_at).total_seconds(), 3)
    elif now - run.started_at > STALE_AFTER:
        out.status = "stale"
    return out


@router.get("/status", response_model=StatusOut)
def system_status(db: Session = Depends(get_db)):
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)

    recent = db.scalars(select(JobRun).order_by(JobRun.started_at.desc()).limit(20)).all()
    finished_7d = db.execute(
        select(JobRun.status, func.count())
        .where(JobRun.started_at >= week_ago, JobRun.finished_at.is_not(None))
        .group_by(JobRun.status)
    ).all()
    counts = dict(finished_7d)
    finished_total = sum(counts.values())

    return StatusOut(
        demo_mode=is_demo_mode(),
        alert_channel=get_sender().channel,
        check_interval_hours=get_settings().check_interval_hours,
        parts_tracked=db.scalar(select(func.count()).select_from(Part).where(Part.active)),
        snapshots_last_24h=db.scalar(
            select(func.count())
            .select_from(PriceSnapshot)
            .where(PriceSnapshot.fetched_at >= now - timedelta(hours=24))
        ),
        deals_total=db.scalar(select(func.count()).select_from(Deal)),
        runs_last_7d=db.scalar(
            select(func.count()).select_from(JobRun).where(JobRun.started_at >= week_ago)
        ),
        success_rate_7d=(
            round(counts.get("success", 0) / finished_total, 4) if finished_total else None
        ),
        last_successful_run_at=db.scalar(
            select(func.max(JobRun.finished_at)).where(JobRun.status == "success")
        ),
        recent_runs=[run_out(r, now) for r in recent],
        recent_errors=[r.last_error for r in recent if r.last_error][:10],
    )
