from collections.abc import Sequence

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.webhook import (
    DeliveryStatus,
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)


class WebhookRepository:
    """
    Репозиторий для работы с webhook-подписками и историей доставок.
    Комбинированный репозиторий для двух связанных моделей.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # === Методы для WebhookSubscription ===

    async def get_subscription_by_id(self, id: int) -> WebhookSubscription | None:
        """Получить подписку по ID."""
        return await self._session.get(WebhookSubscription, id)

    async def get_active_subscriptions_by_event(
        self,
        event_type: WebhookEvent,
    ) -> Sequence[WebhookSubscription]:
        """
        Получить активные подписки по типу события.
        Главный метод для отправки webhooks.
        """
        stmt = select(WebhookSubscription).where(
            and_(
                WebhookSubscription.event_type == event_type,
                WebhookSubscription.is_active == True,  # noqa: E712
            )
        )
        result = await self._session.scalars(stmt)
        return result.all()

    async def get_all_subscriptions(
        self,
        *,
        is_active: bool | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[WebhookSubscription]:
        """Получить все подписки с опциональной фильтрацией."""
        stmt = select(WebhookSubscription)
        if is_active is not None:
            stmt = stmt.where(WebhookSubscription.is_active == is_active)
        stmt = stmt.offset(offset).limit(limit)
        result = await self._session.scalars(stmt)
        return result.all()

    async def create_subscription(
        self,
        name: str,
        target_url: str,
        event_type: WebhookEvent,
        secret: str,
    ) -> WebhookSubscription:
        """Создать новую подписку."""
        subscription = WebhookSubscription(
            name=name,
            target_url=target_url,
            event_type=event_type,
            secret=secret,
        )
        self._session.add(subscription)
        await self._session.flush()
        await self._session.refresh(subscription)
        return subscription

    async def update_subscription(
        self,
        id: int,
        *,
        name: str | None = None,
        target_url: str | None = None,
        secret: str | None = None,
        is_active: bool | None = None,
    ) -> WebhookSubscription | None:
        """Обновить подписку."""
        subscription = await self.get_subscription_by_id(id)
        if subscription is None:
            return None

        if name is not None:
            subscription.name = name
        if target_url is not None:
            subscription.target_url = target_url
        if secret is not None:
            subscription.secret = secret
        if is_active is not None:
            subscription.is_active = is_active

        await self._session.flush()
        await self._session.refresh(subscription)
        return subscription

    async def delete_subscription(self, id: int) -> bool:
        """Удалить подписку. Возвращает True если удалено."""
        subscription = await self.get_subscription_by_id(id)
        if subscription is None:
            return False
        await self._session.delete(subscription)
        await self._session.flush()
        return True

    # === Методы для WebhookDelivery ===

    async def create_delivery(
        self,
        subscription_id: int,
        request_body: str,
    ) -> WebhookDelivery:
        """Создать запись о доставке (pending)."""
        delivery = WebhookDelivery(
            subscription_id=subscription_id,
            request_body=request_body,
            status=DeliveryStatus.PENDING,
        )
        self._session.add(delivery)
        await self._session.flush()
        await self._session.refresh(delivery)
        return delivery

    async def update_delivery(
        self,
        id: int,
        *,
        status: DeliveryStatus,
        response_status: int | None = None,
        response_body: str | None = None,
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> WebhookDelivery | None:
        """Обновить статус доставки после попытки отправки."""
        delivery = await self._session.get(WebhookDelivery, id)
        if delivery is None:
            return None

        delivery.status = status
        if response_status is not None:
            delivery.response_status = response_status
        if response_body is not None:
            delivery.response_body = response_body
        if error_message is not None:
            delivery.error_message = error_message
        if duration_ms is not None:
            delivery.duration_ms = duration_ms

        await self._session.flush()
        await self._session.refresh(delivery)
        return delivery

    async def get_deliveries_by_subscription(
        self,
        subscription_id: int,
        *,
        status: DeliveryStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[WebhookDelivery]:
        """Получить историю доставок подписки."""
        conditions = [WebhookDelivery.subscription_id == subscription_id]
        if status is not None:
            conditions.append(WebhookDelivery.status == status)

        stmt = (
            select(WebhookDelivery)
            .where(and_(*conditions))
            .order_by(WebhookDelivery.attempted_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return result.all()

    async def get_pending_deliveries(
        self,
        *,
        limit: int = 100,
    ) -> Sequence[WebhookDelivery]:
        """Получить pending доставки для обработки."""
        stmt = (
            select(WebhookDelivery)
            .where(WebhookDelivery.status == DeliveryStatus.PENDING)
            .order_by(WebhookDelivery.attempted_at.asc())
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return result.all()

    async def get_failed_deliveries(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[WebhookDelivery]:
        """Получить failed доставки для анализа/retry."""
        stmt = (
            select(WebhookDelivery)
            .where(WebhookDelivery.status == DeliveryStatus.FAILED)
            .order_by(WebhookDelivery.attempted_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return result.all()
