"""Saving price snapshots, one per part per check window."""

from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import PriceSnapshot
from app.services.bestbuy import ProductPrice


def window_start_for(moment: datetime, interval_hours: float) -> datetime:
    """Round `moment` down to the start of its check window.

    Windows are aligned to the Unix epoch, so with a 3-hour interval they are
    00:00, 03:00, 06:00, ... UTC no matter when the scheduler started.
    """
    interval = int(interval_hours * 3600)
    if interval <= 0:
        raise ValueError("interval_hours must be positive")
    seconds = int(moment.timestamp())
    return datetime.fromtimestamp(seconds - seconds % interval, tz=UTC)


def save_snapshot(
    db: Session,
    part_id: int,
    product: ProductPrice,
    fetched_at: datetime,
    window_start: datetime,
) -> PriceSnapshot | None:
    """Insert a snapshot. Returns None if one already exists for this window.

    INSERT ... ON CONFLICT DO NOTHING makes this safe to run twice: the unique
    (part_id, window_start) constraint decides, atomically, even if two workers
    race on the same part.
    """
    stmt = (
        insert(PriceSnapshot)
        .values(
            part_id=part_id,
            price=product.price,
            regular_price=product.regular_price,
            on_sale=product.on_sale,
            in_stock=product.in_stock,
            fetched_at=fetched_at,
            window_start=window_start,
        )
        .on_conflict_do_nothing(constraint="uq_snapshot_part_window")
        .returning(PriceSnapshot.id)
    )
    snapshot_id = db.execute(stmt).scalar()
    db.commit()
    return db.get(PriceSnapshot, snapshot_id) if snapshot_id is not None else None
