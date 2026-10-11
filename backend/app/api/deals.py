from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Deal, Part
from app.schemas import DealOut

router = APIRouter(tags=["deals"])


@router.get("/deals", response_model=list[DealOut])
def recent_deals(
    limit: int = Query(default=50, ge=1, le=500),
    part_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = (
        select(Deal, Part.name, Part.sku)
        .join(Part, Part.id == Deal.part_id)
        .order_by(Deal.detected_at.desc(), Deal.id.desc())
        .limit(limit)
    )
    if part_id is not None:
        query = query.where(Deal.part_id == part_id)
    return [
        DealOut.model_validate({**_columns(deal), "part_name": name, "sku": sku})
        for deal, name, sku in db.execute(query)
    ]


def _columns(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns}
