"""Background tasks.

Fan-out: check_all_prices runs on the Beat schedule and queues one check_part_price
task per active part. Each part is then its own unit of work, so one failing SKU
can't break the whole run, and the tasks can be spread across many workers.

Reliability:
- Retryable Best Buy errors (timeouts, 429, 5xx) retry with exponential backoff
  plus jitter. Permanent errors (404, bad key) fail immediately.
- rate_limit throttles each worker below Best Buy's 5 calls/sec.
- Tasks are idempotent: a re-run in the same window saves nothing new and sends
  no second alert (unique constraints + alerted_at).
- Every run is recorded in job_runs, every part logs a JSON line with its outcome.
"""

import logging
import random
import smtplib
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from celery.signals import after_setup_logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import get_settings
from app.db import SessionLocal
from app.logging_config import configure_logging
from app.models import Deal, Part
from app.services.alerts import format_alert, get_sender
from app.services.bestbuy import RetryableBestBuyError
from app.services.deal_finder import find_deal
from app.services.job_runs import record_part_result, start_run
from app.services.providers import PriceProvider, get_provider
from app.services.snapshots import save_snapshot, window_start_for

logger = logging.getLogger(__name__)

MAX_RETRIES = 5


@after_setup_logger.connect
def _use_json_logs(**_kwargs) -> None:
    configure_logging()


@contextmanager
def get_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def make_provider() -> PriceProvider:
    return get_provider()


def backoff_seconds(retries: int) -> float:
    """5s, 10s, 20s, 40s, 80s (capped at 5 min), plus up to 25% random jitter so
    many failed tasks don't all retry at the same instant."""
    base = min(5 * 2**retries, 300)
    return base + random.uniform(0, base * 0.25)


@celery_app.task(name="app.tasks.check_all_prices")
def check_all_prices() -> int:
    """Queue a price check for every active part. Returns how many were queued."""
    # Every part in this run shares one window, fixed when the run starts. A check
    # that finishes after the boundary still counts toward the right window.
    window_start = window_start_for(datetime.now(UTC), get_settings().check_interval_hours)

    with get_session() as db:
        part_ids = db.scalars(select(Part.id).where(Part.active).order_by(Part.id)).all()
        run = start_run(db, "check_all_prices", len(part_ids))

    for part_id in part_ids:
        check_part_price.delay(part_id, window_start.isoformat(), run.id)

    logger.info(
        "Queued price checks",
        extra={"job_run_id": run.id, "parts": len(part_ids), "window": window_start},
    )
    return len(part_ids)


@celery_app.task(
    bind=True,
    name="app.tasks.check_part_price",
    max_retries=MAX_RETRIES,
    rate_limit=get_settings().bestbuy_rate_limit,
)
def check_part_price(
    self, part_id: int, window_start: str, job_run_id: int | None = None
) -> int | None:
    """Fetch one part's price, save a snapshot, and check for a deal.

    Returns the snapshot id, or None if the part was skipped (inactive, missing,
    or already checked this window)."""
    started = time.monotonic()
    retries = self.request.retries or 0
    log = {"part_id": part_id, "job_run_id": job_run_id, "retries": retries}

    try:
        snapshot_id, outcome = _check_part(part_id, datetime.fromisoformat(window_start))
    except RetryableBestBuyError as exc:
        if retries < MAX_RETRIES:
            delay = backoff_seconds(retries)
            logger.warning(
                "Retrying price check",
                extra={**log, "outcome": "retry", "error": str(exc), "retry_in_s": round(delay)},
            )
            raise self.retry(exc=exc, countdown=delay) from exc
        _record(job_run_id, ok=False, error=f"part {part_id}: {exc}")
        logger.error(
            "Price check failed after retries",
            extra={**log, "outcome": "failed", "error": str(exc), "duration_ms": _ms(started)},
        )
        raise
    except Exception as exc:
        _record(job_run_id, ok=False, error=f"part {part_id}: {exc}")
        logger.error(
            "Price check failed",
            extra={**log, "outcome": "failed", "error": str(exc), "duration_ms": _ms(started)},
        )
        raise

    _record(job_run_id, ok=True)
    logger.info("Price check done", extra={**log, "outcome": outcome, "duration_ms": _ms(started)})
    return snapshot_id


def _check_part(part_id: int, window: datetime) -> tuple[int | None, str]:
    with get_session() as db:
        part = db.get(Part, part_id)
        if part is None or not part.active:
            return None, "skipped_inactive"

        with make_provider() as provider:
            product = provider.get_product(part.sku)

        snapshot = save_snapshot(db, part.id, product, datetime.now(UTC), window)
        if snapshot is None:
            return None, "skipped_duplicate"

        deal = find_deal(db, part, snapshot, get_settings())
        if deal is None:
            return snapshot.id, "saved"

        # Separate task: an email failure retries on its own and can never undo
        # the saved snapshot or deal.
        send_deal_alert.delay(deal.id)
        return snapshot.id, "deal"


def _record(job_run_id: int | None, ok: bool, error: str | None = None) -> None:
    if job_run_id is None:
        return
    with get_session() as db:
        record_part_result(db, job_run_id, ok, error)


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


@celery_app.task(
    name="app.tasks.send_deal_alert",
    autoretry_for=(smtplib.SMTPException, OSError),
    retry_backoff=30,  # 30s, 60s, 120s, ... between attempts
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=MAX_RETRIES,
)
def send_deal_alert(deal_id: int) -> bool:
    """Send the alert for a deal once. Returns False if it was already sent."""
    with get_session() as db:
        deal = db.get(Deal, deal_id)
        if deal is None or deal.alerted_at is not None:
            return False
        part = db.get(Part, deal.part_id)

        sender = get_sender()
        subject, body = format_alert(part, deal)
        sender.send(subject, body)

        deal.alerted_at = datetime.now(UTC)
        db.commit()
        logger.info(
            "Alert sent", extra={"deal_id": deal.id, "part_id": part.id, "channel": sender.channel}
        )
        return True
