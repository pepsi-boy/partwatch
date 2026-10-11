"""Task tests. Best Buy is mocked and the DB is the rolled-back test session."""

from contextlib import contextmanager
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import func, select

from app import tasks
from app.models import JobRun, Part, PriceSnapshot
from app.services.bestbuy import BestBuyClient, ProductNotFound
from app.services.job_runs import start_run

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
    """Fake Best Buy: map SKU -> price, or an int HTTP status to return instead.
    A list is consumed one item per request, e.g. [429, 479.99] fails then succeeds."""
    prices: dict[str, object] = {}
    calls: list[str] = []

    def handler(request):
        sku = request.url.path.rsplit("/", 1)[-1].removesuffix(".json")
        calls.append(sku)
        value = prices.get(sku, 404)
        if isinstance(value, list):
            value = value.pop(0) if len(value) > 1 else value[0]
        if isinstance(value, int):
            return httpx.Response(value)
        return httpx.Response(200, json=product_json(sku, value))

    monkeypatch.setattr(
        tasks,
        "make_provider",
        lambda: BestBuyClient("test-key", transport=httpx.MockTransport(handler)),
    )
    prices["_calls"] = calls
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

    assert [args[0] for args in queued] == [a.id, b.id]
    # Every task in one run shares the same window and job run.
    assert len({args[1] for args in queued}) == 1
    run = use_test_db.get(JobRun, queued[0][2])
    assert (run.status, run.parts_total) == ("running", 2)


def test_one_failing_part_does_not_affect_others(use_test_db, bestbuy):
    good = add_part(use_test_db, "100")
    bad = add_part(use_test_db, "200")
    bestbuy["100"] = 479.99
    bestbuy["200"] = 500

    with pytest.raises(Exception):  # noqa: B017
        tasks.check_part_price(bad.id, WINDOW)
    assert tasks.check_part_price(good.id, WINDOW) is not None
    assert snapshot_count(use_test_db) == 1


@pytest.fixture
def no_backoff(monkeypatch):
    monkeypatch.setattr(tasks, "backoff_seconds", lambda retries: 0)


def run_part(part_id, job_run_id=None):
    """Run check_part_price the way a worker would (retries included), synchronously."""
    return tasks.check_part_price.apply(args=(part_id, WINDOW, job_run_id))


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_error_is_retried_then_succeeds(use_test_db, bestbuy, no_backoff, status):
    part = add_part(use_test_db, "100")
    bestbuy["100"] = [status, status, 479.99]

    result = run_part(part.id)

    assert result.successful()
    assert bestbuy["_calls"].count("100") == 3
    assert snapshot_count(use_test_db) == 1


def test_gives_up_after_max_retries(use_test_db, bestbuy, no_backoff):
    part = add_part(use_test_db, "100")
    bestbuy["100"] = 500

    result = run_part(part.id)

    assert result.failed()
    assert bestbuy["_calls"].count("100") == tasks.MAX_RETRIES + 1
    assert snapshot_count(use_test_db) == 0


def test_permanent_error_is_not_retried(use_test_db, bestbuy, no_backoff):
    part = add_part(use_test_db, "100")  # unknown to the fake -> 404

    assert run_part(part.id).failed()
    assert bestbuy["_calls"].count("100") == 1


def test_job_run_partial_when_one_part_fails(use_test_db, bestbuy, no_backoff):
    good = add_part(use_test_db, "100")
    bad = add_part(use_test_db, "200")
    bestbuy["100"] = 479.99  # 200 -> 404
    run = start_run(use_test_db, "check_all_prices", parts_total=2)

    run_part(good.id, run.id)
    assert use_test_db.get(JobRun, run.id).status == "running"
    run_part(bad.id, run.id)

    use_test_db.refresh(run)
    assert (run.status, run.parts_checked, run.failures) == ("partial", 1, 1)
    assert run.finished_at is not None
    assert "SKU 200 not found" in run.last_error


def test_job_run_success_and_failed_statuses(use_test_db, bestbuy, no_backoff):
    part = add_part(use_test_db, "100")
    bestbuy["100"] = 479.99
    ok_run = start_run(use_test_db, "check_all_prices", parts_total=1)
    run_part(part.id, ok_run.id)

    bad = add_part(use_test_db, "200")
    bad_run = start_run(use_test_db, "check_all_prices", parts_total=1)
    run_part(bad.id, bad_run.id)

    use_test_db.refresh(ok_run)
    use_test_db.refresh(bad_run)
    assert ok_run.status == "success"
    assert bad_run.status == "failed"


def test_empty_run_finishes_immediately(use_test_db):
    run = start_run(use_test_db, "check_all_prices", parts_total=0)
    assert run.status == "success"
    assert run.finished_at is not None


def test_backoff_grows_exponentially_and_is_capped():
    for retries, base in [(0, 5), (1, 10), (2, 20), (3, 40), (10, 300)]:
        delay = tasks.backoff_seconds(retries)
        assert base <= delay <= base * 1.25


def test_part_task_is_rate_limited():
    assert tasks.check_part_price.rate_limit == "4/s"
