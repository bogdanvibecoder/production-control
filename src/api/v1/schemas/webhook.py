from datetime import datetime

from pydantic import Field, HttpUrl

from ....data.models.webhook import DeliveryStatus, WebhookEvent
from .common import BaseSchema, TimestampSchema


class WebhookSubscriptionCreate(BaseSchema):
    """Схема для создания webhook-подписки."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        examples=["Уведомление о завершении партии"],
    )
    target_url: HttpUrl = Field(
        ...,
        examples=["https://example.com/webhook"],
    )
    event_type: WebhookEvent
    secret: str = Field(
        ...,
        min_length=16,
        max_length=255,
    )


class WebhookSubscriptionUpdate(BaseSchema):
    """Схема для обновления webhook-подписки."""

    name: str | None = Field(None, min_length=1, max_length=255)
    target_url: HttpUrl | None = None
    secret: str | None = Field(None, min_length=16, max_length=255)
    is_active: bool | None = None


class WebhookSubscriptionRead(TimestampSchema):
    """Схема для чтения webhook-подписки."""

    id: int
    name: str
    target_url: str
    event_type: WebhookEvent
    is_active: bool


class WebhookSubscriptionFilter(BaseSchema):
    """Query-параметры для фильтрации подписок."""

    event_type: WebhookEvent | None = None
    is_active: bool | None = None


class WebhookDeliveryRead(BaseSchema):
    """Схема для чтения записи о доставке webhook."""

    id: int
    subscription_id: int
    status: DeliveryStatus
    request_body: str
    response_status: int | None = None
    response_body: str | None = None
    error_message: str | None = None
    attempt_number: int
    duration_ms: int | None = None
    attempted_at: datetime


class WebhookDeliveryFilter(BaseSchema):
    """Query-параметры для фильтрации доставок."""

    subscription_id: int | None = Field(None, gt=0)
    status: DeliveryStatus | None = None
