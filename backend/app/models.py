"""Database tables. See CLAUDE.md "Data model" for the intent of each table."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# Money is stored as NUMERIC(10, 2), never float, so $479.99 stays exactly $479.99.
Money = Numeric(10, 2)


class Part(Base):
    __tablename__ = "parts"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Optional: alert when the price is at or below this, regardless of the average.
    target_price: Mapped[Decimal | None] = mapped_column(Money)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    snapshots: Mapped[list["PriceSnapshot"]] = relationship(back_populates="part")


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    __table_args__ = (
        # One snapshot per part per check window. If a check runs twice in the same
        # window (retry, duplicate queue message), the database rejects the second insert.
        UniqueConstraint("part_id", "window_start", name="uq_snapshot_part_window"),
        # Price history queries filter by part and time range.
        Index("ix_snapshot_part_fetched", "part_id", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"))
    price: Mapped[Decimal] = mapped_column(Money)
    regular_price: Mapped[Decimal | None] = mapped_column(Money)
    on_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Start of the check window this snapshot belongs to (fetched_at rounded down
    # to a multiple of CHECK_INTERVAL_HOURS). Backs the uniqueness rule above.
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    part: Mapped[Part] = relationship(back_populates="snapshots")


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"), index=True)
    # Unique: a snapshot can produce at most one deal, so re-running detection is safe.
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("price_snapshots.id", ondelete="CASCADE"), unique=True
    )
    price: Mapped[Decimal] = mapped_column(Money)
    # "below_average" or "below_target" (see services/deals.py)
    reason: Mapped[str] = mapped_column(String(16), server_default="below_average")
    baseline_avg: Mapped[Decimal] = mapped_column(Money)
    percent_below: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # NULL until the email is actually sent. Lets a failed send be retried later
    # without losing the deal.
    alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_name: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="running")
    parts_checked: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
