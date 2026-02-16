"""Unit-тесты для WebhookService."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models.webhook import (
    DeliveryStatus,
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)
from src.domain.exceptions import WebhookNotFoundError
from src.domain.services.webhook_service import WebhookService

# ============================================================================
# Создание подписки
# ============================================================================


class TestCreateSubscription:
    """Тесты создания webhook-подписки."""

    async def test_create_success(self, session: AsyncSession) -> None:
        """Подписка успешно создаётся с корректными данными."""
        service = WebhookService(session)

        sub = await service.create_subscription(
            name="Новая подписка",
            target_url="https://example.com/hook",
            event_type=WebhookEvent.BATCH_CREATED,
            secret="my-secret-key-0123456789",
        )

        assert sub.id is not None
        assert sub.name == "Новая подписка"
        assert sub.target_url == "https://example.com/hook"
        assert sub.event_type == WebhookEvent.BATCH_CREATED
        assert sub.secret == "my-secret-key-0123456789"
        assert sub.is_active is True


# ============================================================================
# Получение подписки
# ============================================================================


class TestGetSubscription:
    """Тесты получения подписок."""

    async def test_get_by_id_success(
        self,
        session: AsyncSession,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Подписка находится по существующему ID."""
        service = WebhookService(session)

        result = await service.get_subscription(webhook_subscription.id)

        assert result.id == webhook_subscription.id
        assert result.name == webhook_subscription.name

    async def test_get_by_id_not_found(self, session: AsyncSession) -> None:
        """Несуществующий ID вызывает WebhookNotFoundError."""
        service = WebhookService(session)

        with pytest.raises(WebhookNotFoundError):
            await service.get_subscription(99999)

    async def test_get_subscriptions_all(
        self,
        session: AsyncSession,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Список подписок возвращается без фильтров."""
        service = WebhookService(session)

        result = await service.get_subscriptions()

        assert len(result) >= 1

    async def test_get_subscriptions_by_event_type(
        self,
        session: AsyncSession,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Фильтрация по event_type возвращает только нужные подписки."""
        service = WebhookService(session)

        result = await service.get_subscriptions(
            event_type=WebhookEvent.BATCH_COMPLETED,
        )

        assert len(result) >= 1
        assert all(sub.event_type == WebhookEvent.BATCH_COMPLETED for sub in result)

    async def test_get_subscriptions_by_active(
        self,
        session: AsyncSession,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Фильтрация по is_active работает корректно."""
        service = WebhookService(session)

        result = await service.get_subscriptions(is_active=True)

        assert len(result) >= 1
        assert all(sub.is_active for sub in result)

    async def test_get_subscriptions_inactive_empty(
        self,
        session: AsyncSession,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Фильтр is_active=False не находит активные подписки."""
        service = WebhookService(session)

        result = await service.get_subscriptions(is_active=False)

        assert len(result) == 0


# ============================================================================
# Обновление подписки
# ============================================================================


class TestUpdateSubscription:
    """Тесты обновления подписки."""

    async def test_update_name(
        self,
        session: AsyncSession,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Обновление имени подписки работает."""
        service = WebhookService(session)

        updated = await service.update_subscription(webhook_subscription.id, name="Обновлённое имя")

        assert updated.name == "Обновлённое имя"

    async def test_update_target_url(
        self,
        session: AsyncSession,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Обновление URL подписки работает."""
        service = WebhookService(session)

        updated = await service.update_subscription(
            webhook_subscription.id,
            target_url="https://new-url.com/webhook",
        )

        assert updated.target_url == "https://new-url.com/webhook"

    async def test_deactivate_subscription(
        self,
        session: AsyncSession,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Деактивация подписки работает."""
        service = WebhookService(session)

        updated = await service.update_subscription(webhook_subscription.id, is_active=False)

        assert updated.is_active is False

    async def test_update_not_found_raises(self, session: AsyncSession) -> None:
        """Обновление несуществующей подписки вызывает ошибку."""
        service = WebhookService(session)

        with pytest.raises(WebhookNotFoundError):
            await service.update_subscription(99999, name="X")


# ============================================================================
# Удаление подписки
# ============================================================================


class TestDeleteSubscription:
    """Тесты удаления подписки."""

    async def test_delete_success(
        self,
        session: AsyncSession,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Существующая подписка успешно удаляется."""
        service = WebhookService(session)

        await service.delete_subscription(webhook_subscription.id)

        with pytest.raises(WebhookNotFoundError):
            await service.get_subscription(webhook_subscription.id)

    async def test_delete_not_found_raises(self, session: AsyncSession) -> None:
        """Удаление несуществующей подписки вызывает ошибку."""
        service = WebhookService(session)

        with pytest.raises(WebhookNotFoundError):
            await service.delete_subscription(99999)


# ============================================================================
# Trigger event (создание доставок)
# ============================================================================


class TestTriggerEvent:
    """Тесты инициирования webhook-событий."""

    async def test_trigger_creates_deliveries(
        self,
        session: AsyncSession,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """При событии создаются записи доставки для активных подписок."""
        service = WebhookService(session)

        deliveries = await service.trigger_event(
            event_type=WebhookEvent.BATCH_COMPLETED,
            payload={"batch_id": 1, "status": "completed"},
        )

        assert len(deliveries) == 1
        assert deliveries[0].subscription_id == webhook_subscription.id
        assert deliveries[0].status == DeliveryStatus.PENDING
        assert '"batch_id": 1' in deliveries[0].request_body

    async def test_trigger_no_subscriptions_returns_empty(self, session: AsyncSession) -> None:
        """Событие без подписок возвращает пустой список."""
        service = WebhookService(session)

        deliveries = await service.trigger_event(
            event_type=WebhookEvent.BATCH_CREATED,
            payload={"batch_id": 1},
        )

        assert deliveries == []

    async def test_trigger_inactive_subscription_ignored(
        self,
        session: AsyncSession,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Деактивированная подписка не получает доставки."""
        service = WebhookService(session)

        # Деактивируем подписку
        await service.update_subscription(webhook_subscription.id, is_active=False)

        deliveries = await service.trigger_event(
            event_type=WebhookEvent.BATCH_COMPLETED,
            payload={"batch_id": 1},
        )

        assert deliveries == []

    async def test_trigger_multiple_subscriptions(self, session: AsyncSession) -> None:
        """Несколько подписок на одно событие — все получают доставки."""
        service = WebhookService(session)

        # Создаём 3 подписки на одно событие
        for i in range(3):
            await service.create_subscription(
                name=f"Sub-{i}",
                target_url=f"https://example.com/hook-{i}",
                event_type=WebhookEvent.BATCH_STARTED,
                secret=f"secret-key-number-{i:04d}",
            )

        deliveries = await service.trigger_event(
            event_type=WebhookEvent.BATCH_STARTED,
            payload={"batch_id": 5},
        )

        assert len(deliveries) == 3


# ============================================================================
# История доставок
# ============================================================================


class TestGetDeliveries:
    """Тесты получения истории доставок."""

    async def test_get_deliveries_success(
        self,
        session: AsyncSession,
        webhook_subscription: WebhookSubscription,
        webhook_delivery: WebhookDelivery,
    ) -> None:
        """История доставок возвращается для существующей подписки."""
        service = WebhookService(session)

        result = await service.get_deliveries(webhook_subscription.id)

        assert len(result) >= 1
        assert result[0].subscription_id == webhook_subscription.id

    async def test_get_deliveries_subscription_not_found(self, session: AsyncSession) -> None:
        """Запрос доставок для несуществующей подписки вызывает ошибку."""
        service = WebhookService(session)

        with pytest.raises(WebhookNotFoundError):
            await service.get_deliveries(99999)
