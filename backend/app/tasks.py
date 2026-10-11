"""Background tasks.

Fan-out: check_all_prices runs on the Beat schedule and queues one check_part_price
task per active part. Each part is then its own unit of work, so one failing SKU
can't break the whole run, and the tasks can be spread across many workers.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import get_settings
from app.db import SessionLocal
from app.models import Part
from app.services.bestbuy import BestBuyClient
from app.services.snapshots import save_snapshot, window_start_for

logger = logging.getLogger(__name__)


@contextmanager
def get_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def make_client() -> BestBuyClient:
    return BestBuyClient(get_settings().bestbuy_api_key)


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

        with make_client() as client:
            product = client.get_product(part.sku)

        snapshot = save_snapshot(db, part.id, product, datetime.now(UTC), window)
        if snapshot is None:
            logger.info("Part %s (%s) already checked for window %s", part.id, part.sku, window)
            return None

        logger.info("Part %s (%s) price %s", part.id, part.sku, snapshot.price)
        return snapshot.id
