import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import price_provider, require_admin
from app.config import get_settings
from app.db import get_db
from app.models import Part, PriceSnapshot
from app.schemas import PartCreate, PartOut, PartUpdate, PricePoint
from app.services import deals
from app.services.bestbuy import BestBuyError, ProductNotFound, RetryableBestBuyError
from app.services.providers import PriceProvider
from app.services.snapshots import window_start_for

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/parts", tags=["parts"])

ABOVE_AVERAGE_PERCENT = Decimal("5")


def price_status(part: Part, price: Decimal | None, avg: Decimal | None, pct) -> str:
    if price is None:
        return "unknown"
    threshold = Decimal(str(get_settings().deal_threshold_percent))
    if part.target_price is not None and price <= part.target_price:
        return "deal"
    if avg is None:
        return "normal"
    if pct >= threshold:
        return "deal"
    if pct <= -ABOVE_AVERAGE_PERCENT:
        return "above_average"
    return "normal"


def with_prices(db: Session, parts: list[Part]) -> list[PartOut]:
    """Attach current price and 30-day average. Two queries total, not two per part."""
    ids = [p.id for p in parts]
    if not ids:
        return []
    # DISTINCT ON keeps the first row per part_id, i.e. its newest snapshot.
    latest = {
        s.part_id: s
        for s in db.scalars(
            select(PriceSnapshot)
            .where(PriceSnapshot.part_id.in_(ids))
            .distinct(PriceSnapshot.part_id)
            .order_by(PriceSnapshot.part_id, PriceSnapshot.fetched_at.desc())
        )
    }
    since = datetime.now(UTC) - timedelta(days=30)
    averages = dict(
        db.execute(
            select(PriceSnapshot.part_id, func.avg(PriceSnapshot.price))
            .where(PriceSnapshot.part_id.in_(ids), PriceSnapshot.fetched_at >= since)
            .group_by(PriceSnapshot.part_id)
        ).all()
    )

    out = []
    for part in parts:
        snap = latest.get(part.id)
        avg = averages.get(part.id)
        avg = avg.quantize(deals.CENTS) if avg is not None else None
        price = snap.price if snap else None
        pct = deals.percent_below(price, avg) if price is not None and avg else None
        item = PartOut.model_validate(part)
        item.current_price = price
        item.regular_price = snap.regular_price if snap else None
        item.in_stock = snap.in_stock if snap else None
        item.last_checked_at = snap.fetched_at if snap else None
        item.avg_30d = avg
        item.percent_vs_avg = pct
        item.price_status = price_status(part, price, avg, pct)
        out.append(item)
    return out


def get_part_or_404(db: Session, part_id: int) -> Part:
    part = db.get(Part, part_id)
    if part is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Part not found")
    return part


@router.get("", response_model=list[PartOut])
def list_parts(include_inactive: bool = True, db: Session = Depends(get_db)):
    query = select(Part).order_by(Part.category, Part.name)
    if not include_inactive:
        query = query.where(Part.active)
    return with_prices(db, list(db.scalars(query)))


@router.get("/{part_id}", response_model=PartOut)
def get_part(part_id: int, db: Session = Depends(get_db)):
    return with_prices(db, [get_part_or_404(db, part_id)])[0]


@router.post(
    "",
    response_model=PartOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_part(
    body: PartCreate,
    db: Session = Depends(get_db),
    provider: PriceProvider = Depends(price_provider),
):
    """Track a new part. The SKU is looked up first, so typos are rejected."""
    if db.scalar(select(Part.id).where(Part.sku == body.sku)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"SKU {body.sku} is already tracked")
    try:
        product = provider.get_product(body.sku)
    except ProductNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"SKU {body.sku} not found") from None
    except RetryableBestBuyError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Best Buy is unavailable, try again shortly"
        ) from None
    except BestBuyError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None

    part = Part(
        sku=body.sku,
        name=body.name or product.name or f"SKU {body.sku}",
        category=body.category.lower(),
        target_price=body.target_price,
    )
    db.add(part)
    db.commit()
    _queue_first_check(part.id)
    return with_prices(db, [part])[0]


def _queue_first_check(part_id: int) -> None:
    """Fetch the first price now instead of waiting for the next scheduled run.
    Best effort: if the queue is down, the scheduled run picks the part up later."""
    from app.tasks import check_part_price

    window = window_start_for(datetime.now(UTC), get_settings().check_interval_hours)
    try:
        check_part_price.delay(part_id, window.isoformat())
    except Exception:
        logger.warning("Could not queue first check", extra={"part_id": part_id}, exc_info=True)


@router.patch("/{part_id}", response_model=PartOut, dependencies=[Depends(require_admin)])
def update_part(part_id: int, body: PartUpdate, db: Session = Depends(get_db)):
    """Pause/resume tracking (`active`), rename, or set/clear the target price."""
    part = get_part_or_404(db, part_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "name" and value is None:
            continue
        setattr(part, field, value)
    db.commit()
    return with_prices(db, [part])[0]


@router.delete(
    "/{part_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)]
)
def delete_part(part_id: int, db: Session = Depends(get_db)):
    """Stop tracking and delete the part with its price history and deals.
    To keep the history, PATCH {"active": false} instead."""
    db.delete(get_part_or_404(db, part_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{part_id}/prices", response_model=list[PricePoint])
def price_history(
    part_id: int, days: int = Query(default=30, ge=1, le=365), db: Session = Depends(get_db)
):
    get_part_or_404(db, part_id)
    since = datetime.now(UTC) - timedelta(days=days)
    return db.scalars(
        select(PriceSnapshot)
        .where(PriceSnapshot.part_id == part_id, PriceSnapshot.fetched_at >= since)
        .order_by(PriceSnapshot.fetched_at)
    ).all()
