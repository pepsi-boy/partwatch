"""job_runs bookkeeping: one row per fan-out run, closed by the last part task."""

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import JobRun


def start_run(db: Session, task_name: str, parts_total: int) -> JobRun:
    run = JobRun(task_name=task_name, parts_total=parts_total, status="running")
    if parts_total == 0:
        run.status, run.finished_at = "success", datetime.now(UTC)
    db.add(run)
    db.commit()
    return run


def record_part_result(db: Session, run_id: int, ok: bool, error: str | None = None) -> None:
    """Count one finished part (atomic increment, safe with many workers) and close
    the run once every part is accounted for."""
    values = {
        "parts_checked": JobRun.parts_checked + (1 if ok else 0),
        "failures": JobRun.failures + (0 if ok else 1),
    }
    if error:
        values["last_error"] = error[:500]
    row = db.execute(
        update(JobRun)
        .where(JobRun.id == run_id)
        .values(**values)
        .returning(JobRun.parts_checked, JobRun.failures, JobRun.parts_total)
    ).first()
    if row is None:
        db.commit()
        return

    checked, failures, total = row
    if checked + failures >= total:
        status = "success" if failures == 0 else "failed" if checked == 0 else "partial"
        # finished_at IS NULL: if two tasks finish at once, only the first closes the run.
        db.execute(
            update(JobRun)
            .where(JobRun.id == run_id, JobRun.finished_at.is_(None))
            .values(status=status, finished_at=datetime.now(UTC))
        )
    db.commit()
