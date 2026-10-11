from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models import Part, PriceSnapshot
from app.seed import backfill_history, seed_parts
from app.seed_data import STARTER_PARTS

NOW = datetime(2026, 10, 11, 13, 30, tzinfo=UTC)


@pytest.fixture
def demo_mode(monkeypatch):
    monkeypatch.setattr(get_settings(), "bestbuy_api_key", "")


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_seed_parts_is_idempotent(db):
    assert seed_parts(db) == len(STARTER_PARTS)
    assert seed_parts(db) == 0
    assert count(db, Part) == len(STARTER_PARTS)


def test_seed_sets_target_prices(db):
    seed_parts(db)
    gpu = db.scalar(select(Part).where(Part.sku == "0000001"))
    assert str(gpu.target_price) == "499.99"


def test_backfill_one_snapshot_per_window_and_idempotent(db, demo_mode):
    seed_parts(db)

    added = backfill_history(db, days=2, interval_hours=3, now=NOW)

    # 2 days back from 12:00 (NOW's window) is 16 windows per part, current one excluded.
    assert added == 16 * len(STARTER_PARTS)
    assert backfill_history(db, days=2, interval_hours=3, now=NOW) == 0
    latest = db.scalar(select(func.max(PriceSnapshot.window_start)))
    assert latest == datetime(2026, 10, 11, 9, tzinfo=UTC)


def test_backfill_refused_with_real_api_key(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "bestbuy_api_key", "real-key")
    with pytest.raises(RuntimeError):
        backfill_history(db, days=1, interval_hours=3, now=NOW)
