from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models import Part
from app.services.bestbuy import ProductPrice
from app.services.snapshots import save_snapshot, window_start_for

PRODUCT = ProductPrice(
    sku="6521430",
    name="RTX 4070",
    price=Decimal("479.99"),
    regular_price=Decimal("549.99"),
    on_sale=True,
    in_stock=True,
)


@pytest.mark.parametrize(
    ("moment", "expected_hour"),
    [
        (datetime(2026, 10, 11, 0, 0, tzinfo=UTC), 0),
        (datetime(2026, 10, 11, 2, 59, 59, tzinfo=UTC), 0),
        (datetime(2026, 10, 11, 3, 0, tzinfo=UTC), 3),
        (datetime(2026, 10, 11, 23, 30, tzinfo=UTC), 21),
    ],
)
def test_window_start_rounds_down_to_interval(moment, expected_hour):
    assert window_start_for(moment, 3) == moment.replace(hour=expected_hour, minute=0, second=0)


def test_window_start_supports_fractional_hours():
    moment = datetime(2026, 10, 11, 10, 44, tzinfo=UTC)
    assert window_start_for(moment, 0.5) == moment.replace(minute=30)


def test_window_start_rejects_non_positive_interval():
    with pytest.raises(ValueError):
        window_start_for(datetime.now(UTC), 0)


def test_save_snapshot_is_idempotent_per_window(db):
    part = Part(sku="6521430", name="RTX 4070", category="gpu")
    db.add(part)
    db.flush()
    window = datetime(2026, 10, 11, 12, tzinfo=UTC)

    first = save_snapshot(db, part.id, PRODUCT, window, window)
    second = save_snapshot(db, part.id, PRODUCT, window, window)

    assert first is not None
    assert first.price == Decimal("479.99")
    assert second is None
    assert len(part.snapshots) == 1
