"""Request and response shapes for the API (Pydantic validates and documents them;
they also drive the Swagger docs at /docs)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

# Stored as exact Decimals; sent as plain JSON numbers so charts can use them directly.
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class PartCreate(BaseModel):
    sku: str = Field(pattern=r"^\d{1,16}$", examples=["6521430"])
    category: str = Field(min_length=1, max_length=64, examples=["gpu"])
    name: str | None = Field(
        default=None, max_length=255, description="Defaults to the name Best Buy returns"
    )
    target_price: Money | None = Field(default=None, gt=0, examples=[499.99])


class PartUpdate(BaseModel):
    active: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    target_price: Money | None = Field(default=None, gt=0)


class PartOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    category: str
    active: bool
    target_price: Money | None
    created_at: datetime
    current_price: Money | None = None
    regular_price: Money | None = None
    in_stock: bool | None = None
    last_checked_at: datetime | None = None
    avg_30d: Money | None = None
    percent_vs_avg: Money | None = Field(
        default=None, description="Positive = below average (cheaper than usual)"
    )
    price_status: Literal["deal", "normal", "above_average", "unknown"] = "unknown"


class PricePoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fetched_at: datetime
    price: Money
    regular_price: Money | None
    on_sale: bool
    in_stock: bool


class DealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    part_id: int
    part_name: str
    sku: str
    price: Money
    baseline_avg: Money
    percent_below: Money
    reason: str
    detected_at: datetime
    alerted_at: datetime | None


class JobRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    parts_total: int
    parts_checked: int
    failures: int
    last_error: str | None
    duration_seconds: float | None = None


class StatusOut(BaseModel):
    demo_mode: bool
    alert_channel: Literal["email", "log"]
    check_interval_hours: float
    parts_tracked: int
    snapshots_last_24h: int
    deals_total: int
    runs_last_7d: int
    success_rate_7d: float | None = Field(description="Share of finished runs with no failures")
    last_successful_run_at: datetime | None
    recent_runs: list[JobRunOut]
    recent_errors: list[str]
