from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from .common import BaseSchema


class TaskStatus(str, Enum):
    """Статусы Celery-задачи."""

    PENDING = "PENDING"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    RETRY = "RETRY"
    REVOKED = "REVOKED"


class TaskResponse(BaseSchema):
    """Ответ с информацией о Celery-задаче."""

    task_id: str
    status: TaskStatus
    result: Any = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress: int | None = Field(None, ge=0, le=100)


class TaskCreate(BaseSchema):
    """Ответ при постановке задачи в очередь."""

    task_id: str
    status: TaskStatus = TaskStatus.PENDING


class ImportTaskRequest(BaseSchema):
    """Запрос на импорт продукции из файла."""

    batch_id: int = Field(..., gt=0)
    file_name: str = Field(..., min_length=1)


class ExportTaskRequest(BaseSchema):
    """Запрос на экспорт данных."""

    export_format: str = Field(
        "xlsx",
        pattern=r"^(xlsx|csv)$",
    )
    date_from: datetime | None = None
    date_to: datetime | None = None


class AggregationTaskRequest(BaseSchema):
    """Запрос на массовую агрегацию продукции."""

    batch_id: int = Field(..., gt=0)
    codes: list[str] = Field(
        ...,
        min_length=1,
        max_length=10000,
    )
