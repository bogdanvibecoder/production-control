from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_async_session
from ....core.exceptions import AppException
from ....data.models.webhook import DeliveryStatus, WebhookEvent
from ....domain.exceptions import WebhookNotFoundError
from ....domain.services.webhook_service import WebhookService
from ..schemas.webhook import (
    WebhookDeliveryRead,
    WebhookSubscriptionCreate,
    WebhookSubscriptionRead,
    WebhookSubscriptionUpdate,
)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


# === Управление подписками ===


@router.post(
    "/",
    response_model=WebhookSubscriptionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать webhook-подписку",
    responses={
        201: {"description": "Подписка успешно создана"},
    },
)
async def create_subscription(
    data: WebhookSubscriptionCreate,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> WebhookSubscriptionRead:
    """
    Создать новую webhook-подписку.

    **Обязательные поля:**
    - `name`: название подписки (для удобства в UI)
    - `target_url`: URL, куда отправлять POST-запросы
    - `event_type`: тип события (batch.created, batch.completed и т.д.)
    - `secret`: секретный ключ для HMAC-подписи (минимум 16 символов)

    **Доступные события:**
    - `batch.created` — партия создана
    - `batch.started` — партия запущена
    - `batch.completed` — партия завершена
    - `batch.cancelled` — партия отменена
    - `product.aggregated` — продукция агрегирована

    **Возвращает:** созданную подписку (без секрета).
    """
    service = WebhookService(session)

    subscription = await service.create_subscription(
        name=data.name,
        target_url=str(data.target_url),
        event_type=data.event_type,
        secret=data.secret,
    )

    return WebhookSubscriptionRead.model_validate(subscription)


@router.get(
    "/",
    response_model=list[WebhookSubscriptionRead],
    summary="Получить список подписок",
    responses={
        200: {"description": "Список webhook-подписок"},
    },
)
async def get_subscriptions(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    event_type: Annotated[WebhookEvent | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> list[WebhookSubscriptionRead]:
    """
    Получить список webhook-подписок с фильтрацией.

    **Query-параметры:**
    - `offset`: смещение (по умолчанию 0)
    - `limit`: количество записей (от 1 до 500, по умолчанию 100)
    - `event_type`: фильтр по типу события
    - `is_active`: фильтр по активности (true/false)

    **Возвращает:** массив подписок (без секретов).
    """
    service = WebhookService(session)

    subscriptions = await service.get_subscriptions(
        offset=offset,
        limit=limit,
        event_type=event_type,
        is_active=is_active,
    )

    return [WebhookSubscriptionRead.model_validate(sub) for sub in subscriptions]


@router.get(
    "/{subscription_id}",
    response_model=WebhookSubscriptionRead,
    summary="Получить подписку по ID",
    responses={
        200: {"description": "Подписка найдена"},
        404: {"description": "Подписка не найдена"},
    },
)
async def get_subscription(
    subscription_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> WebhookSubscriptionRead:
    """
    Получить webhook-подписку по ID.

    **Path-параметры:**
    - `subscription_id`: ID подписки

    **Возвращает:** подписку со всеми полями (кроме секрета).
    """
    service = WebhookService(session)

    try:
        subscription = await service.get_subscription(subscription_id)
    except WebhookNotFoundError as e:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Webhook-подписка не найдена",
            details=e.details,
        ) from e

    return WebhookSubscriptionRead.model_validate(subscription)


@router.patch(
    "/{subscription_id}",
    response_model=WebhookSubscriptionRead,
    summary="Обновить подписку",
    responses={
        200: {"description": "Подписка обновлена"},
        404: {"description": "Подписка не найдена"},
    },
)
async def update_subscription(
    subscription_id: int,
    data: WebhookSubscriptionUpdate,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> WebhookSubscriptionRead:
    """
    Обновить webhook-подписку.

    **Path-параметры:**
    - `subscription_id`: ID подписки

    **Поля для обновления (все опциональны):**
    - `name`: название подписки
    - `target_url`: URL для отправки
    - `secret`: новый секретный ключ
    - `is_active`: включить/выключить подписку

    **Примечание:** `event_type` изменить нельзя —
    удалите подписку и создайте новую.

    **Возвращает:** обновлённую подписку (без секрета).
    """
    service = WebhookService(session)

    try:
        subscription = await service.update_subscription(
            subscription_id,
            name=data.name,
            target_url=str(data.target_url) if data.target_url is not None else None,
            secret=data.secret,
            is_active=data.is_active,
        )
    except WebhookNotFoundError as e:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Webhook-подписка не найдена",
            details=e.details,
        ) from e

    return WebhookSubscriptionRead.model_validate(subscription)


@router.delete(
    "/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить подписку",
    responses={
        204: {"description": "Подписка успешно удалена"},
        404: {"description": "Подписка не найдена"},
    },
)
async def delete_subscription(
    subscription_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """
    Удалить webhook-подписку по ID.

    **Path-параметры:**
    - `subscription_id`: ID подписки

    **Возвращает:** HTTP 204 (пустой ответ) при успехе.

    **Примечание:** При удалении подписки также удаляется
    вся история доставок (CASCADE).
    """
    service = WebhookService(session)

    try:
        await service.delete_subscription(subscription_id)
    except WebhookNotFoundError as e:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Webhook-подписка не найдена",
            details=e.details,
        ) from e


# === История доставок ===


@router.get(
    "/{subscription_id}/deliveries",
    response_model=list[WebhookDeliveryRead],
    summary="Получить историю доставок",
    responses={
        200: {"description": "История доставок подписки"},
        404: {"description": "Подписка не найдена"},
    },
)
async def get_deliveries(
    subscription_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    status_filter: Annotated[DeliveryStatus | None, Query(alias="status")] = None,
) -> list[WebhookDeliveryRead]:
    """
    Получить историю доставок для конкретной подписки.

    **Path-параметры:**
    - `subscription_id`: ID подписки

    **Query-параметры:**
    - `offset`: смещение (по умолчанию 0)
    - `limit`: количество записей (от 1 до 500, по умолчанию 100)
    - `status`: фильтр по статусу доставки (pending, success, failed, retrying)

    **Возвращает:** массив записей о доставках, отсортированных
    от новых к старым.
    """
    service = WebhookService(session)

    try:
        deliveries = await service.get_deliveries(
            subscription_id,
            offset=offset,
            limit=limit,
            status=status_filter,
        )
    except WebhookNotFoundError as e:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Webhook-подписка не найдена",
            details=e.details,
        ) from e

    return [WebhookDeliveryRead.model_validate(delivery) for delivery in deliveries]
