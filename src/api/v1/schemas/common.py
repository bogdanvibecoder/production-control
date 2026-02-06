from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

SchemaType = TypeVar("SchemaType")


class BaseSchema(BaseModel):
    """Базовая схема с общей конфигурацией для всех схем."""

    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
    )


class TimestampSchema(BaseSchema):
    """Миксин для схем с временными метками."""

    created_at: datetime
    updated_at: datetime


class SuccessResponse(BaseSchema):
    """Стандартный ответ об успешной операции."""

    success: bool = True
    message: str


class ErrorResponse(BaseSchema):
    """Стандартный ответ об ошибке."""

    error: str
    message: str
    details: Any = None


class PaginatedResponse(BaseSchema, Generic[SchemaType]):
    """Обёртка для пагинированных списков."""

    items: list[SchemaType]
    total: int
    offset: int
    limit: int
