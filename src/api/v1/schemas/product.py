from datetime import datetime

from pydantic import Field

from ....data.models.product import ProductStatus
from .common import BaseSchema, TimestampSchema


class ProductCreate(BaseSchema):
    """Схема для создания единицы продукции."""

    code: str = Field(
        ...,
        min_length=1,
        max_length=255,
        examples=["PRD-2026-000001"],
    )
    batch_id: int = Field(..., gt=0)
    product_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        examples=["bottle"],
    )
    extra_data: str | None = None
    produced_at: datetime | None = None


class ProductUpdate(BaseSchema):
    """Схема для обновления единицы продукции."""

    status: ProductStatus | None = None
    product_type: str | None = Field(
        None,
        min_length=1,
        max_length=50,
    )
    extra_data: str | None = None


class ProductBulkStatusUpdate(BaseSchema):
    """Схема для массового обновления статуса продукции."""

    codes: list[str] = Field(
        ...,
        min_length=1,
        max_length=1000,
    )
    new_status: ProductStatus


class ProductRead(TimestampSchema):
    """Схема для чтения единицы продукции."""

    id: int
    code: str
    batch_id: int
    status: ProductStatus
    product_type: str
    extra_data: str | None = None
    produced_at: datetime


class ProductFilter(BaseSchema):
    """Query-параметры для фильтрации списка продукции."""

    batch_id: int | None = Field(None, gt=0)
    status: ProductStatus | None = None
    product_type: str | None = None
