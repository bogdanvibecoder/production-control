import json
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...data.models.webhook import (
    DeliveryStatus,
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)
from ...data.repositories.webhook_repository import WebhookRepository
from ..exceptions import WebhookNotFoundError


class WebhookService:
    """Сервис бизнес-логики для работы с webhook-подписками."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = WebhookRepository(session)

    # === Управление подписками ===

    async def get_subscription(
        self,
        subscription_id: int,
    ) -> WebhookSubscription:
        """Получить подписку по ID."""
        sub = await self._repo.get_subscription_by_id(subscription_id)
        if sub is None:
            raise WebhookNotFoundError(
                details={"subscription_id": subscription_id},
            )
        return sub

    async def get_subscriptions(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        event_type: WebhookEvent | None = None,
        is_active: bool | None = None,
    ) -> Sequence[WebhookSubscription]:
        """Получить список подписок с фильтрацией."""
        if event_type is not None:
            return await self._repo.get_active_subscriptions_by_event(
                event_type,
            )
        return await self._repo.get_all_subscriptions(
            is_active=is_active,
            offset=offset,
            limit=limit,
        )

    async def create_subscription(
        self,
        *,
        name: str,
        target_url: str,
        event_type: WebhookEvent,
        secret: str,
    ) -> WebhookSubscription:
        """Создать новую webhook-подписку."""
        sub = await self._repo.create_subscription(
            name=name,
            target_url=target_url,
            event_type=event_type,
            secret=secret,
        )
        await self._session.commit()
        return sub

    async def update_subscription(
        self,
        subscription_id: int,
        *,
        name: str | None = None,
        target_url: str | None = None,
        secret: str | None = None,
        is_active: bool | None = None,
    ) -> WebhookSubscription:
        """Обновить webhook-подписку."""
        sub = await self._repo.update_subscription(
            subscription_id,
            name=name,
            target_url=target_url,
            secret=secret,
            is_active=is_active,
        )
        if sub is None:
            raise WebhookNotFoundError(
                details={"subscription_id": subscription_id},
            )
        await self._session.commit()
        return sub

    async def delete_subscription(self, subscription_id: int) -> None:
        """Удалить webhook-подписку."""
        deleted = await self._repo.delete_subscription(subscription_id)
        if not deleted:
            raise WebhookNotFoundError(
                details={"subscription_id": subscription_id},
            )
        await self._session.commit()

    # === Работа с событиями ===

    async def trigger_event(
        self,
        event_type: WebhookEvent,
        payload: dict[str, Any],
    ) -> list[WebhookDelivery]:
        """
        Инициировать отправку webhook по событию.
        Создаёт записи доставки для всех активных подписок.
        """
        subscriptions = await self._repo.get_active_subscriptions_by_event(
            event_type,
        )

        if not subscriptions:
            return []

        request_body = json.dumps(payload, ensure_ascii=False, default=str)

        deliveries: list[WebhookDelivery] = []
        for sub in subscriptions:
            delivery = await self._repo.create_delivery(
                subscription_id=sub.id,
                request_body=request_body,
            )
            deliveries.append(delivery)

        await self._session.commit()
        return deliveries

    # === История доставок ===

    async def get_deliveries(
        self,
        subscription_id: int,
        *,
        offset: int = 0,
        limit: int = 100,
        status: DeliveryStatus | None = None,
    ) -> Sequence[WebhookDelivery]:
        """Получить историю доставок для подписки."""
        await self.get_subscription(subscription_id)

        return await self._repo.get_deliveries_by_subscription(
            subscription_id,
            status=status,
            offset=offset,
            limit=limit,
        )
