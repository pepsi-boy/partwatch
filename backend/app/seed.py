"""Seed the starter parts, and in demo mode optionally backfill price history.

    python -m app.seed                    # add starter parts (safe to re-run)
    python -m app.seed --backfill-days 30 # demo mode: also add 30 days of mock prices

Backfilling gives deal detection a 30-day baseline right away, instead of waiting
a month for real history. It's refused when a real Best Buy key is configured,
so fake prices never mix with real ones.
"""

import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import Part
from app.seed_data import STARTER_PARTS
from app.services.providers import MockBestBuyProvider, is_demo_mode
from app.services.snapshots import save_snapshot, window_start_for


def seed_parts(db: Session) -> int:
    """Insert starter parts that aren't already tracked. Returns how many were added."""
    rows = [{k: p[k] for k in ("sku", "name", "category", "target_price")} for p in STARTER_PARTS]
    stmt = insert(Part).values(rows).on_conflict_do_nothing(index_elements=["sku"])
    # rowcount isn't reliable for multi-row inserts with psycopg, so count RETURNING rows.
    added = len(db.execute(stmt.returning(Part.id)).all())
    db.commit()
    return added


def backfill_history(
    db: Session,
    days: int,
    interval_hours: float,
    now: datetime | None = None,
) -> int:
    """Add mock snapshots for every active part, one per past check window."""
    if not is_demo_mode():
        raise RuntimeError("Refusing to backfill mock prices: BESTBUY_API_KEY is set")

    now = now or datetime.now(UTC)
    mock = MockBestBuyProvider()
    step = timedelta(hours=interval_hours)
    current_window = window_start_for(now, interval_hours)
    windows = []
    window = window_start_for(now - timedelta(days=days), interval_hours)
    # Stop before the current window so the next scheduled check fills it for real.
    while window < current_window:
        windows.append(window)
        window += step

    added = 0
    for part in db.scalars(select(Part).where(Part.active)).all():
        for window in windows:
            product = mock.get_product(part.sku, at=window)
            if save_snapshot(db, part.id, product, window, window) is not None:
                added += 1
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--backfill-days", type=int, default=0)
    args = parser.parse_args()

    with SessionLocal() as db:
        print(f"Added {seed_parts(db)} starter parts")
        if args.backfill_days:
            interval = get_settings().check_interval_hours
            added = backfill_history(db, args.backfill_days, interval)
            print(f"Backfilled {added} mock snapshots over {args.backfill_days} days")


if __name__ == "__main__":
    main()
