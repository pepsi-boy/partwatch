"""Deal finding + alert sending against the test DB. SMTP is always faked."""

import smtplib
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import func, select

from app import tasks
from app.config import Settings, get_settings
from app.models import Deal, Part, PriceSnapshot
from app.services import alerts
from app.services.alerts import EmailSender, LogSender, format_alert, get_sender
from app.services.deal_finder import find_deal

T0 = datetime(2026, 10, 1, tzinfo=UTC)
SETTINGS = Settings(deal_threshold_percent=10, min_snapshots_for_deal=5)


def add_part(db, target=None) -> Part:
    part = Part(sku="6521430", name="RTX 4070", category="gpu", target_price=target)
    db.add(part)
    db.flush()
    return part


def add_snapshot(db, part, price, hours) -> PriceSnapshot:
    at = T0 + timedelta(hours=hours)
    snap = PriceSnapshot(
        part_id=part.id, price=D(price), on_sale=False, in_stock=True, fetched_at=at,
        window_start=at,
    )  # fmt: skip
    db.add(snap)
    db.flush()
    return snap


def run_prices(db, part, prices, start=0) -> list[Deal | None]:
    """Save each price as the next 3-hour snapshot and run deal detection on it."""
    out = []
    for i, price in enumerate(prices, start=start):
        out.append(find_deal(db, part, add_snapshot(db, part, price, 3 * i), SETTINGS))
    return out


def deal_count(db) -> int:
    return db.scalar(select(func.count()).select_from(Deal))


def test_drop_after_stable_history_records_deal(db):
    part = add_part(db)
    results = run_prices(db, part, ["550"] * 6 + ["479.99"])

    assert results[:6] == [None] * 6
    deal = results[-1]
    assert deal.price == D("479.99")
    assert deal.baseline_avg == D("550.00")
    assert deal.reason == "below_average"
    assert deal.alerted_at is None


def test_new_part_with_little_history_does_not_trigger(db):
    part = add_part(db)
    assert run_prices(db, part, ["550", "550", "300"]) == [None] * 3


def test_find_deal_twice_for_same_snapshot_records_once(db):
    part = add_part(db)
    run_prices(db, part, ["550"] * 6)
    snap = add_snapshot(db, part, "479.99", 100)

    assert find_deal(db, part, snap, SETTINGS) is not None
    assert find_deal(db, part, snap, SETTINGS) is None
    assert deal_count(db) == 1


def test_no_realert_until_further_drop(db):
    part = add_part(db)
    results = run_prices(db, part, ["550"] * 6 + ["479.99", "479.99", "485.00", "449.99"])
    assert [r is not None for r in results[6:]] == [True, False, False, True]


def test_realerts_after_price_recovers(db):
    part = add_part(db)
    # Sale, recovery to the average, then the same sale price again.
    results = run_prices(db, part, ["550"] * 6 + ["479.99", "560.00", "479.99"])
    assert [r is not None for r in results[6:]] == [True, False, True]


def test_history_older_than_30_days_ignored(db):
    part = add_part(db)
    # 6 old snapshots at $800 are outside the window; the recent 5 at $550 set the baseline.
    run_prices(db, part, ["800"] * 6)
    recent = [
        find_deal(db, part, add_snapshot(db, part, p, 24 * 31 + 3 * i), SETTINGS)
        for i, p in enumerate(["550"] * 5 + ["520"])
    ]
    assert recent == [None] * 6  # $520 is only 5.5% below $550


def test_target_price_deal(db):
    part = add_part(db, target=D("499.99"))
    deal = run_prices(db, part, ["520", "499.99"])[-1]
    assert deal.reason == "below_target"


def test_format_alert_mentions_price_and_percent(db):
    part = add_part(db)
    deal = run_prices(db, part, ["550"] * 6 + ["479.99"])[-1]
    subject, body = format_alert(part, deal)
    assert subject == "RTX 4070 is $479.99, 12.73% below its 30-day average"
    assert "$550.00" in body


def test_format_alert_for_target_deal(db):
    part = add_part(db, target=D("499.99"))
    deal = run_prices(db, part, ["520", "499.99"])[-1]
    assert format_alert(part, deal)[0] == "RTX 4070 is $499.99, at or below your $499.99 target"


def test_get_sender_uses_email_only_when_configured():
    assert isinstance(get_sender(Settings(smtp_user="", smtp_password="")), LogSender)
    configured = Settings(smtp_user="me@gmail.com", smtp_password="app-pw", alert_email_to="me@x")
    assert isinstance(get_sender(configured), EmailSender)


class FakeSMTP:
    """Stands in for smtplib.SMTP. Records what would have been sent."""

    sent: list = []
    fail_with: Exception | None = None

    def __init__(self, host, port, timeout):
        self.host, self.port, self.timeout = host, port, timeout

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        if FakeSMTP.fail_with:
            raise FakeSMTP.fail_with
        FakeSMTP.sent.append(msg)


@pytest.fixture
def fake_smtp(monkeypatch):
    FakeSMTP.sent = []
    FakeSMTP.fail_with = None
    monkeypatch.setattr(alerts.smtplib, "SMTP", FakeSMTP)
    s = get_settings()
    monkeypatch.setattr(s, "smtp_user", "omar@gmail.com")
    monkeypatch.setattr(s, "smtp_password", "app-password")
    monkeypatch.setattr(s, "alert_email_to", "omar@gmail.com")
    return FakeSMTP


@pytest.fixture
def deal(db, monkeypatch):
    @contextmanager
    def session():
        yield db

    monkeypatch.setattr(tasks, "get_session", session)
    part = add_part(db)
    return run_prices(db, part, ["550"] * 6 + ["479.99"])[-1]


def test_send_deal_alert_emails_once(db, deal, fake_smtp):
    assert tasks.send_deal_alert(deal.id) is True
    assert tasks.send_deal_alert(deal.id) is False  # already alerted

    assert len(fake_smtp.sent) == 1
    msg = fake_smtp.sent[0]
    assert msg["To"] == "omar@gmail.com"
    assert "12.73% below" in msg["Subject"]
    assert db.get(Deal, deal.id).alerted_at is not None


def test_failed_email_keeps_deal_and_is_retryable(db, deal, fake_smtp):
    fake_smtp.fail_with = smtplib.SMTPServerDisconnected("connection lost")

    with pytest.raises(smtplib.SMTPServerDisconnected):
        tasks.send_deal_alert(deal.id)

    saved = db.get(Deal, deal.id)
    assert saved is not None
    assert saved.alerted_at is None  # so the retry will send it
    assert smtplib.SMTPException in tasks.send_deal_alert.autoretry_for

    fake_smtp.fail_with = None
    assert tasks.send_deal_alert(deal.id) is True
    assert len(fake_smtp.sent) == 1


def test_log_sender_used_without_smtp(db, deal, monkeypatch, caplog):
    monkeypatch.setattr(get_settings(), "smtp_user", "")
    caplog.set_level("INFO")

    assert tasks.send_deal_alert(deal.id) is True
    assert "DEAL ALERT: RTX 4070 is $479.99" in caplog.text


def test_check_part_price_queues_alert_on_deal(db, deal, monkeypatch):
    """End to end through check_part_price, with the mock provider forced to a low price."""
    from app.services.bestbuy import ProductPrice

    part = db.get(Part, deal.part_id)
    product = ProductPrice(part.sku, part.name, D("399.99"), D("599.99"), True, True)

    class Provider:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def get_product(self, sku):
            return product

    queued = []
    monkeypatch.setattr(tasks, "make_provider", Provider)
    monkeypatch.setattr(tasks.send_deal_alert, "delay", queued.append)

    window = (T0 + timedelta(days=2)).isoformat()
    tasks.check_part_price(part.id, window)

    assert len(queued) == 1
    assert db.get(Deal, queued[0]).price == D("399.99")
