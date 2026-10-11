"""Background tasks.

Fan-out: check_all_prices runs on the Beat schedule and queues one check_part_price
task per active part. Each part is then its own unit of work, so one failing SKU
can't break the whole run, and the tasks can be spread across many workers.
"""

import logging
import smtplib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import get_settings
from app.db import SessionLocal
from app.models import Deal, Part
from app.services.alerts import format_alert, get_sender
from app.services.deal_finder import find_deal
from app.services.providers import PriceProvider, get_provider
from app.services.snapshots import save_snapshot, window_start_for

logger = logging.getLogger(__name__)


@contextmanager
def get_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def make_provider() -> PriceProvider:
    return get_provider()


@celery_app.task(name="app.tasks.check_all_prices")
def check_all_prices() -> int:
    """Queue a price check for every active part. Returns how many were queued."""
    # Every part in this run shares one window, fixed when the run starts. A check
    # that finishes after the boundary still counts toward the right window.
    window_start = window_start_for(datetime.now(UTC), get_settings().check_interval_hours)

    with get_session() as db:
        part_ids = db.scalars(select(Part.id).where(Part.active).order_by(Part.id)).all()

    for part_id in part_ids:
        check_part_price.delay(part_id, window_start.isoformat())

    logger.info("Queued %d price checks for window %s", len(part_ids), window_start)
    return len(part_ids)


@celery_app.task(name="app.tasks.check_part_price")
def check_part_price(part_id: int, window_start: str) -> int | None:
    """Fetch one part's price and save a snapshot. Returns the snapshot id, or None
    if the part is gone or inactive, or this window already has a snapshot."""
    window = datetime.fromisoformat(window_start)

    with get_session() as db:
        part = db.get(Part, part_id)
        if part is None or not part.active:
            logger.info("Skipping part %s: missing or inactive", part_id)
            return None

        with make_provider() as provider:
            product = provider.get_product(part.sku)

        snapshot = save_snapshot(db, part.id, product, datetime.now(UTC), window)
        if snapshot is None:
            logger.info("Part %s (%s) already checked for window %s", part.id, part.sku, window)
            return None

        logger.info("Part %s (%s) price %s", part.id, part.sku, snapshot.price)

        deal = find_deal(db, part, snapshot, get_settings())
        if deal is not None:
            logger.info("Deal found for part %s: deal %s", part.id, deal.id)
            # Separate task: an email failure retries on its own and can never undo
            # the saved snapshot or deal.
            send_deal_alert.delay(deal.id)

        return snapshot.id


@celery_app.task(
    name="app.tasks.send_deal_alert",
    autoretry_for=(smtplib.SMTPException, OSError),
    retry_backoff=30,  # 30s, 60s, 120s, ... between attempts
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
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
        logger.info("Alert sent for deal %s via %s", deal.id, sender.channel)
        return True
