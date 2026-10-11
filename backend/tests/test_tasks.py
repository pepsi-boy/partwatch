"""Task tests. Best Buy is mocked and the DB is the rolled-back test session."""

from contextlib import contextmanager
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import func, select

from app import tasks
from app.models import Part, PriceSnapshot
from app.services.bestbuy import BestBuyClient, ProductNotFound

WINDOW = datetime(2026, 10, 11, 12, tzinfo=UTC).isoformat()


def product_json(sku, price):
    return {
        "sku": int(sku),
        "name": f"Part {sku}",
        "salePrice": price,
        "regularPrice": price + 50,
        "onSale": True,
        "onlineAvailability": True,
    }


@pytest.fixture
def use_test_db(db, monkeypatch):
    @contextmanager
    def session():
        yield db

    monkeypatch.setattr(tasks, "get_session", session)
    return db


@pytest.fixture
def bestbuy(monkeypatch):
    """Fake Best Buy: map SKU -> price (or an int HTTP status to return instead)."""
    prices: dict[str, object] = {}

    def handler(request):
        sku = request.url.path.rsplit("/", 1)[-1].removesuffix(".json")
        value = prices.get(sku, 404)
        if isinstance(value, int):
            return httpx.Response(value)
        return httpx.Response(200, json=product_json(sku, value))

    monkeypatch.setattr(
        tasks,
        "make_provider",
        lambda: BestBuyClient("test-key", transport=httpx.MockTransport(handler)),
    )
    return prices


def add_part(db, sku, active=True) -> Part:
    part = Part(sku=sku, name=f"Part {sku}", category="gpu", active=active)
    db.add(part)
    db.flush()
    return part


def snapshot_count(db) -> int:
    return db.scalar(select(func.count()).select_from(PriceSnapshot))


def test_check_part_price_saves_snapshot(use_test_db, bestbuy):
    part = add_part(use_test_db, "100")
    bestbuy["100"] = 479.99

    snapshot_id = tasks.check_part_price(part.id, WINDOW)

    snapshot = use_test_db.get(PriceSnapshot, snapshot_id)
    assert str(snapshot.price) == "479.99"
    assert snapshot.window_start.isoformat() == WINDOW


def test_check_part_price_twice_in_window_saves_once(use_test_db, bestbuy):
    part = add_part(use_test_db, "100")
    bestbuy["100"] = 479.99

    assert tasks.check_part_price(part.id, WINDOW) is not None
    assert tasks.check_part_price(part.id, WINDOW) is None
    assert snapshot_count(use_test_db) == 1


def test_check_part_price_skips_inactive_and_missing(use_test_db, bestbuy):
    part = add_part(use_test_db, "100", active=False)
    bestbuy["100"] = 479.99

    assert tasks.check_part_price(part.id, WINDOW) is None
    assert tasks.check_part_price(999_999, WINDOW) is None
    assert snapshot_count(use_test_db) == 0


def test_check_part_price_raises_on_api_failure(use_test_db, bestbuy):
    part = add_part(use_test_db, "100")  # not in fake catalog -> 404

    with pytest.raises(ProductNotFound):
        tasks.check_part_price(part.id, WINDOW)
    assert snapshot_count(use_test_db) == 0


def test_check_all_prices_fans_out_one_task_per_active_part(use_test_db, monkeypatch):
    a = add_part(use_test_db, "100")
    b = add_part(use_test_db, "200")
    add_part(use_test_db, "300", active=False)
    queued = []
    monkeypatch.setattr(tasks.check_part_price, "delay", lambda *args: queued.append(args))

    assert tasks.check_all_prices() == 2

    assert [part_id for part_id, _ in queued] == [a.id, b.id]
    # Every task in one run shares the same window.
    assert len({window for _, window in queued}) == 1


def test_one_failing_part_does_not_affect_others(use_test_db, bestbuy):
    good = add_part(use_test_db, "100")
    bad = add_part(use_test_db, "200")
    bestbuy["100"] = 479.99
    bestbuy["200"] = 500

    with pytest.raises(Exception):  # noqa: B017
        tasks.check_part_price(bad.id, WINDOW)
    assert tasks.check_part_price(good.id, WINDOW) is not None
    assert snapshot_count(use_test_db) == 1
