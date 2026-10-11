"""Database side of deal detection: load history, ask services/deals.py, save the result."""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Deal, Part, PriceSnapshot
from app.services import deals

BASELINE_DAYS = 30


def find_deal(db: Session, part: Part, snapshot: PriceSnapshot, settings: Settings) -> Deal | None:
    """Evaluate a new snapshot and record a Deal if it is one. Safe to call twice for
    the same snapshot: deals.snapshot_id is unique, so the second call adds nothing."""
    history = db.scalars(
        select(PriceSnapshot.price).where(
            PriceSnapshot.part_id == part.id,
            PriceSnapshot.window_start < snapshot.window_start,
            PriceSnapshot.window_start >= snapshot.window_start - timedelta(days=BASELINE_DAYS),
        )
    ).all()

    decision = deals.evaluate(
        snapshot.price,
        history,
        threshold_percent=Decimal(str(settings.deal_threshold_percent)),
        min_snapshots=settings.min_snapshots_for_deal,
        target_price=part.target_price,
        active_deal_price=_active_deal_price(db, part, snapshot),
    )
    if not decision.is_deal:
        return None

    stmt = (
        insert(Deal)
        .values(
            part_id=part.id,
            snapshot_id=snapshot.id,
            price=snapshot.price,
            reason=decision.reason,
            baseline_avg=decision.baseline_avg,
            percent_below=decision.percent_below,
        )
        .on_conflict_do_nothing(index_elements=["snapshot_id"])
        .returning(Deal.id)
    )
    deal_id = db.execute(stmt).scalar()
    db.commit()
    return db.get(Deal, deal_id) if deal_id is not None else None


def _active_deal_price(db: Session, part: Part, snapshot: PriceSnapshot) -> Decimal | None:
    """Price of the part's last deal, unless the price has recovered since then."""
    last = db.execute(
        select(Deal, PriceSnapshot.window_start)
        .join(PriceSnapshot, Deal.snapshot_id == PriceSnapshot.id)
        .where(Deal.part_id == part.id, PriceSnapshot.window_start < snapshot.window_start)
        .order_by(PriceSnapshot.window_start.desc())
        .limit(1)
    ).first()
    if last is None:
        return None
    deal, deal_window = last

    prices_since = db.scalars(
        select(PriceSnapshot.price).where(
            PriceSnapshot.part_id == part.id,
            PriceSnapshot.window_start > deal_window,
            PriceSnapshot.window_start < snapshot.window_start,
        )
    ).all()
    rearmed = deals.is_rearmed(
        reason=deal.reason,
        deal_baseline=deal.baseline_avg,
        target_price=part.target_price,
        prices_since_deal=prices_since,
    )
    return None if rearmed else deal.price
