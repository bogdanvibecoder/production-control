from datetime import datetime
from decimal import Decimal

from pydantic import Field

from ....data.models.batch import BatchStatus
from .common import BaseSchema, TimestampSchema


class BatchCreate(BaseSchema):
    """Схема для создания партии (POST /batches)."""

    number: str = Field(
        ...,
        min_length=1,
        max_length=100,
        examples=["B-2026-001"],
    )
    work_center_id: int = Field(..., gt=0)
    shift_date: datetime
    shift_number: int = Field(..., ge=1, le=3)
    planned_quantity: Decimal = Field(
        ...,
        gt=0,
        max_digits=15,
        decimal_places=3,
    )


class BatchUpdate(BaseSchema):
    """Схема для обновления партии (PATCH /batches/{id})."""

    shift_date: datetime | None = None
    shift_number: int | None = Field(None, ge=1, le=3)
    planned_quantity: Decimal | None = Field(
        None,
        gt=0,
        max_digits=15,
        decimal_places=3,
    )
    status: BatchStatus | None = None
    actual_quantity: Decimal | None = Field(
        None,
        ge=0,
        max_digits=15,
        decimal_places=3,
    )


class BatchRead(TimestampSchema):
    """Схема для чтения партии (GET /batches/{id})."""

    id: int
    number: str
    work_center_id: int
    shift_date: datetime
    shift_number: int
    status: BatchStatus
    planned_quantity: Decimal
    actual_quantity: Decimal
    started_at: datetime | None = None
    completed_at: datetime | None = None


class BatchFilter(BaseSchema):
    """Query-параметры для фильтрации списка партий."""

    status: BatchStatus | None = None
    work_center_id: int | None = Field(None, gt=0)
    shift_number: int | None = Field(None, ge=1, le=3)
    date_from: datetime | None = None
    date_to: datetime | None = None
