"""API integration tests against the test Postgres database."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from app.api.deps import price_provider
from app.main import app
from app.models import Deal, JobRun, Part, PriceSnapshot
from app.services.bestbuy import ProductNotFound, RetryableBestBuyError
from app.services.providers import MockBestBuyProvider

NOW = datetime.now(UTC)


def add_part(db, sku="100", **kw) -> Part:
    part = Part(sku=sku, name=kw.pop("name", f"Part {sku}"), category="gpu", **kw)
    db.add(part)
    db.flush()
    return part


def add_prices(db, part, prices, hours_apart=3):
    """Prices oldest first, the last one 1 hour ago."""
    snaps = []
    for i, price in enumerate(prices):
        at = NOW - timedelta(hours=1 + hours_apart * (len(prices) - 1 - i))
        snap = PriceSnapshot(
            part_id=part.id, price=D(price), regular_price=D("599.99"), on_sale=False,
            in_stock=True, fetched_at=at, window_start=at,
        )  # fmt: skip
        db.add(snap)
        snaps.append(snap)
    db.flush()
    return snaps


@pytest.fixture
def provider():
    """Override the price provider used by POST /parts."""

    def use(p):
        app.dependency_overrides[price_provider] = lambda: p

    return use


class FailingProvider:
    def __init__(self, exc):
        self.exc = exc

    def get_product(self, sku):
        raise self.exc


# ---- auth ----


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/parts"), ("patch", "/parts/1"), ("delete", "/parts/1"), ("post", "/run-checks")],
)
def test_write_routes_require_token(client, method, path):
    assert client.request(method, path, json={}).status_code == 401
    bad = {"Authorization": "Bearer wrong"}
    assert client.request(method, path, json={}, headers=bad).status_code == 401


def test_write_routes_disabled_when_no_token_configured(client, admin, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "admin_token", "")
    resp = client.post("/parts", json={"sku": "1", "category": "gpu"}, headers=admin)
    assert resp.status_code == 503


# ---- parts ----


def test_list_parts_with_price_summary(client, db):
    part = add_part(db, target_price=D("450.00"))
    add_prices(db, part, ["550"] * 5 + ["479.99"])

    [item] = client.get("/parts").json()

    assert item["sku"] == "100"
    assert item["current_price"] == 479.99
    assert item["avg_30d"] == 538.33
    assert item["percent_vs_avg"] == 10.84
    assert item["price_status"] == "deal"
    assert item["target_price"] == 450.0


@pytest.mark.parametrize(
    ("last", "status"), [("540", "normal"), ("700", "above_average"), ("440", "deal")]
)
def test_price_status_badge(client, db, last, status):
    part = add_part(db)
    add_prices(db, part, ["550"] * 5 + [last])
    assert client.get(f"/parts/{part.id}").json()["price_status"] == status


def test_part_without_prices_is_unknown(client, db):
    add_part(db)
    item = client.get("/parts").json()[0]
    assert item["current_price"] is None
    assert item["price_status"] == "unknown"


def test_list_can_hide_inactive(client, db):
    add_part(db, "100")
    add_part(db, "200", active=False)
    assert len(client.get("/parts").json()) == 2
    assert [p["sku"] for p in client.get("/parts?include_inactive=false").json()] == ["100"]


def test_create_part_looks_up_name(client, admin, provider):
    provider(MockBestBuyProvider())
    resp = client.post(
        "/parts", json={"sku": "0000001", "category": "GPU", "target_price": 499.99}, headers=admin
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "NVIDIA GeForce RTX 5070 12GB"
    assert body["category"] == "gpu"
    assert body["target_price"] == 499.99
    assert body["active"] is True


def test_create_part_keeps_given_name(client, admin, provider):
    provider(MockBestBuyProvider())
    resp = client.post(
        "/parts", json={"sku": "0000001", "category": "gpu", "name": "My GPU"}, headers=admin
    )
    assert resp.json()["name"] == "My GPU"


def test_create_duplicate_sku_conflicts(client, db, admin, provider):
    provider(MockBestBuyProvider())
    add_part(db, "0000001")
    resp = client.post("/parts", json={"sku": "0000001", "category": "gpu"}, headers=admin)
    assert resp.status_code == 409


@pytest.mark.parametrize(
    ("exc", "code"),
    [(ProductNotFound("nope"), 404), (RetryableBestBuyError("slow"), 503)],
)
def test_create_part_maps_provider_errors(client, admin, provider, exc, code):
    provider(FailingProvider(exc))
    resp = client.post("/parts", json={"sku": "123", "category": "gpu"}, headers=admin)
    assert resp.status_code == code


@pytest.mark.parametrize(
    "body",
    [
        {"sku": "abc", "category": "gpu"},
        {"sku": "123", "category": ""},
        {"sku": "123", "category": "gpu", "target_price": -5},
        {"category": "gpu"},
    ],
)
def test_create_part_validates_input(client, admin, body):
    assert client.post("/parts", json=body, headers=admin).status_code == 422


def test_patch_pauses_tracking_and_sets_target(client, db, admin):
    part = add_part(db)
    resp = client.patch(
        f"/parts/{part.id}", json={"active": False, "target_price": 399.99}, headers=admin
    )
    assert resp.status_code == 200
    assert resp.json()["active"] is False
    assert resp.json()["target_price"] == 399.99


def test_patch_can_clear_target(client, db, admin):
    part = add_part(db, target_price=D("400"))
    resp = client.patch(f"/parts/{part.id}", json={"target_price": None}, headers=admin)
    assert resp.json()["target_price"] is None


def test_delete_removes_part_and_history(client, db, admin):
    part = add_part(db)
    [snap] = add_prices(db, part, ["500"])
    db.add(Deal(part_id=part.id, snapshot_id=snap.id, price=D("500"), reason="below_target",
                baseline_avg=D("550"), percent_below=D("9.09")))  # fmt: skip
    db.flush()

    part_id, snap_id = part.id, snap.id

    assert client.delete(f"/parts/{part_id}", headers=admin).status_code == 204
    assert client.get(f"/parts/{part_id}").status_code == 404
    db.expire_all()
    assert db.get(PriceSnapshot, snap_id) is None


def test_unknown_part_is_404(client, admin):
    assert client.get("/parts/999999").status_code == 404
    assert client.get("/parts/999999/prices").status_code == 404
    assert client.patch("/parts/999999", json={}, headers=admin).status_code == 404
    assert client.delete("/parts/999999", headers=admin).status_code == 404


# ---- price history, deals, status ----


def test_price_history_filters_by_days_oldest_first(client, db):
    part = add_part(db)
    add_prices(db, part, ["600", "550", "500"], hours_apart=24 * 4)  # 8 days, 4 days, 1h ago

    all_points = client.get(f"/parts/{part.id}/prices?days=30").json()
    recent = client.get(f"/parts/{part.id}/prices?days=7").json()

    assert [p["price"] for p in all_points] == [600.0, 550.0, 500.0]
    assert [p["price"] for p in recent] == [550.0, 500.0]
    assert client.get(f"/parts/{part.id}/prices?days=0").status_code == 422


def test_deals_newest_first_with_part_info(client, db):
    part = add_part(db, name="RTX 4070")
    snaps = add_prices(db, part, ["480", "470"])
    for snap, at in zip(snaps, [NOW - timedelta(hours=5), NOW], strict=True):
        db.add(Deal(part_id=part.id, snapshot_id=snap.id, price=snap.price, reason="below_average",
                    baseline_avg=D("550"), percent_below=D("12.73"), detected_at=at))  # fmt: skip
    db.flush()

    deals = client.get("/deals").json()

    assert [d["price"] for d in deals] == [470.0, 480.0]
    assert deals[0]["part_name"] == "RTX 4070"
    assert deals[0]["alerted_at"] is None
    assert len(client.get("/deals?limit=1").json()) == 1


def test_status_summarizes_runs(client, db):
    part = add_part(db)
    add_prices(db, part, ["500"])
    for status, minutes in [("success", 300), ("partial", 120), ("success", 10)]:
        start = NOW - timedelta(minutes=minutes)
        db.add(JobRun(task_name="check_all_prices", status=status, started_at=start,
                      finished_at=start + timedelta(seconds=2), parts_total=2,
                      parts_checked=2 if status == "success" else 1,
                      failures=0 if status == "success" else 1,
                      last_error=None if status == "success" else "part 9: HTTP 500"))  # fmt: skip
    db.add(JobRun(task_name="check_all_prices", status="running",
                  started_at=NOW - timedelta(hours=3), parts_total=1))  # fmt: skip
    db.flush()

    body = client.get("/status").json()

    assert body["parts_tracked"] == 1
    assert body["snapshots_last_24h"] == 1
    assert body["runs_last_7d"] == 4
    assert body["success_rate_7d"] == round(2 / 3, 4)
    assert body["recent_runs"][0]["duration_seconds"] == 2.0
    unfinished = [r for r in body["recent_runs"] if r["finished_at"] is None]
    assert [r["status"] for r in unfinished] == ["stale"]
    assert body["recent_errors"] == ["part 9: HTTP 500"]
    assert body["demo_mode"] in (True, False)


def test_status_with_no_runs(client):
    body = client.get("/status").json()
    assert body["success_rate_7d"] is None
    assert body["last_successful_run_at"] is None


def test_run_checks_queues_fan_out(client, admin, monkeypatch):
    from app import tasks

    queued = []
    monkeypatch.setattr(tasks.check_all_prices, "delay", lambda: queued.append(True))
    assert client.post("/run-checks", headers=admin).status_code == 202
    assert queued == [True]


def test_dashboard_and_docs_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "PartWatch" in page.text
    assert client.get("/docs").status_code == 200
    assert "/parts" in client.get("/openapi.json").json()["paths"]
