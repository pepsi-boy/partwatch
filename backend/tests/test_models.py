from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.models import Deal, Part, PriceSnapshot

WINDOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def make_part(db, sku="6521430") -> Part:
    part = Part(sku=sku, name="RTX 4070", category="gpu")
    db.add(part)
    db.flush()
    return part


def make_snapshot(db, part, price="549.99", window=WINDOW) -> PriceSnapshot:
    snap = PriceSnapshot(
        part_id=part.id,
        price=Decimal(price),
        regular_price=Decimal("599.99"),
        on_sale=True,
        in_stock=True,
        fetched_at=window,
        window_start=window,
    )
    db.add(snap)
    db.flush()
    return snap


def test_part_defaults(db):
    part = make_part(db)
    db.refresh(part)
    assert part.active is True
    assert part.created_at is not None


def test_sku_is_unique(db):
    make_part(db, sku="123")
    with pytest.raises(IntegrityError):
        make_part(db, sku="123")


def test_price_stored_exactly(db):
    snap = make_snapshot(db, make_part(db), price="479.99")
    db.refresh(snap)
    assert snap.price == Decimal("479.99")


def test_duplicate_snapshot_in_same_window_rejected(db):
    part = make_part(db)
    make_snapshot(db, part)
    with pytest.raises(IntegrityError):
        make_snapshot(db, part)


def test_snapshots_in_different_windows_allowed(db):
    part = make_part(db)
    make_snapshot(db, part, window=WINDOW)
    make_snapshot(db, part, window=WINDOW.replace(hour=15))
    assert len(part.snapshots) == 2


def test_one_deal_per_snapshot(db):
    part = make_part(db)
    snap = make_snapshot(db, part)
    for _ in range(2):
        db.add(
            Deal(
                part_id=part.id,
                snapshot_id=snap.id,
                price=snap.price,
                baseline_avg=Decimal("600.00"),
                percent_below=Decimal("8.33"),
            )
        )
    with pytest.raises(IntegrityError):
        db.flush()


def test_migrations_downgrade_and_upgrade_cleanly(alembic_config, db_engine):
    command.downgrade(alembic_config, "base")
    assert "parts" not in inspect(db_engine).get_table_names()
    command.upgrade(alembic_config, "head")
    tables = set(inspect(db_engine).get_table_names())
    assert {"parts", "price_snapshots", "deals", "job_runs"} <= tables
