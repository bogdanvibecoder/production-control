"""Integration-тесты для API webhooks (/api/v1/webhooks)."""

from httpx import AsyncClient

from src.data.models.webhook import WebhookDelivery, WebhookSubscription

API = "/api/v1/webhooks"


# ============================================================================
# POST /webhooks — создание подписки
# ============================================================================


class TestCreateWebhookAPI:
    """Тесты создания webhook-подписки через API."""

    async def test_create_201(self, client: AsyncClient) -> None:
        """Успешное создание → 201 + корректный JSON."""
        response = await client.post(
            API,
            json={
                "name": "API Webhook",
                "target_url": "https://example.com/hook",
                "event_type": "batch.completed",
                "secret": "super-secret-key-1234",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "API Webhook"
        assert data["event_type"] == "batch.completed"
        assert data["is_active"] is True
        assert "id" in data
        assert "created_at" in data
        # Секрет НЕ возвращается в ответе
        assert "secret" not in data

    async def test_create_short_secret_422(self, client: AsyncClient) -> None:
        """Короткий секрет (< 16 символов) → 422."""
        response = await client.post(
            API,
            json={
                "name": "Bad Secret",
                "target_url": "https://example.com/hook",
                "event_type": "batch.created",
                "secret": "short",
            },
        )

        assert response.status_code == 422

    async def test_create_invalid_url_422(self, client: AsyncClient) -> None:
        """Невалидный URL → 422."""
        response = await client.post(
            API,
            json={
                "name": "Bad URL",
                "target_url": "not-a-url",
                "event_type": "batch.created",
                "secret": "valid-secret-key-1234",
            },
        )

        assert response.status_code == 422

    async def test_create_invalid_event_type_422(self, client: AsyncClient) -> None:
        """Невалидный тип события → 422."""
        response = await client.post(
            API,
            json={
                "name": "Bad Event",
                "target_url": "https://example.com/hook",
                "event_type": "invalid.event",
                "secret": "valid-secret-key-1234",
            },
        )

        assert response.status_code == 422


# ============================================================================
# GET /webhooks — список подписок
# ============================================================================


class TestGetWebhooksAPI:
    """Тесты получения списка подписок."""

    async def test_get_list_200(
        self,
        client: AsyncClient,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Список подписок → 200 + массив."""
        response = await client.get(API)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_get_list_filter_by_event(
        self,
        client: AsyncClient,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Фильтр по event_type работает."""
        response = await client.get(API, params={"event_type": "batch.completed"})

        assert response.status_code == 200
        data = response.json()
        for item in data:
            assert item["event_type"] == "batch.completed"

    async def test_get_list_filter_by_active(
        self,
        client: AsyncClient,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Фильтр по is_active работает."""
        response = await client.get(API, params={"is_active": True})

        assert response.status_code == 200
        data = response.json()
        for item in data:
            assert item["is_active"] is True


# ============================================================================
# GET /webhooks/{id} — получение по ID
# ============================================================================


class TestGetWebhookByIdAPI:
    """Тесты получения подписки по ID."""

    async def test_get_by_id_200(
        self,
        client: AsyncClient,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Существующий ID → 200."""
        response = await client.get(f"{API}/{webhook_subscription.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == webhook_subscription.id
        assert data["name"] == webhook_subscription.name
        assert "secret" not in data

    async def test_get_by_id_404(self, client: AsyncClient) -> None:
        """Несуществующий ID → 404."""
        response = await client.get(f"{API}/99999")

        assert response.status_code == 404


# ============================================================================
# PATCH /webhooks/{id} — обновление
# ============================================================================


class TestUpdateWebhookAPI:
    """Тесты обновления подписки через API."""

    async def test_update_name_200(
        self,
        client: AsyncClient,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Обновление имени → 200."""
        response = await client.patch(
            f"{API}/{webhook_subscription.id}",
            json={"name": "Новое имя"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Новое имя"

    async def test_deactivate_200(
        self,
        client: AsyncClient,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Деактивация подписки → 200."""
        response = await client.patch(
            f"{API}/{webhook_subscription.id}",
            json={"is_active": False},
        )

        assert response.status_code == 200
        assert response.json()["is_active"] is False

    async def test_update_target_url_200(
        self,
        client: AsyncClient,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Обновление URL → 200."""
        response = await client.patch(
            f"{API}/{webhook_subscription.id}",
            json={"target_url": "https://new-endpoint.com/webhook"},
        )

        assert response.status_code == 200
        assert "new-endpoint.com" in response.json()["target_url"]

    async def test_update_not_found_404(self, client: AsyncClient) -> None:
        """Обновление несуществующей подписки → 404."""
        response = await client.patch(
            f"{API}/99999",
            json={"name": "X"},
        )

        assert response.status_code == 404


# ============================================================================
# DELETE /webhooks/{id} — удаление
# ============================================================================


class TestDeleteWebhookAPI:
    """Тесты удаления подписки через API."""

    async def test_delete_204(
        self,
        client: AsyncClient,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Успешное удаление → 204."""
        response = await client.delete(f"{API}/{webhook_subscription.id}")
        assert response.status_code == 204

        # Проверяем, что удалено
        check = await client.get(f"{API}/{webhook_subscription.id}")
        assert check.status_code == 404

    async def test_delete_not_found_404(self, client: AsyncClient) -> None:
        """Удаление несуществующей подписки → 404."""
        response = await client.delete(f"{API}/99999")
        assert response.status_code == 404


# ============================================================================
# GET /webhooks/{id}/deliveries — история доставок
# ============================================================================


class TestDeliveriesAPI:
    """Тесты получения истории доставок."""

    async def test_get_deliveries_200(
        self,
        client: AsyncClient,
        webhook_subscription: WebhookSubscription,
        webhook_delivery: WebhookDelivery,
    ) -> None:
        """История доставок → 200 + массив."""
        response = await client.get(f"{API}/{webhook_subscription.id}/deliveries")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["subscription_id"] == webhook_subscription.id
        assert data[0]["status"] == "pending"
        assert "request_body" in data[0]
        assert "attempt_number" in data[0]

    async def test_get_deliveries_empty(
        self,
        client: AsyncClient,
        webhook_subscription: WebhookSubscription,
    ) -> None:
        """Подписка без доставок → 200 + пустой массив."""
        response = await client.get(f"{API}/{webhook_subscription.id}/deliveries")

        assert response.status_code == 200
        assert response.json() == []

    async def test_get_deliveries_subscription_not_found_404(self, client: AsyncClient) -> None:
        """Доставки несуществующей подписки → 404."""
        response = await client.get(f"{API}/99999/deliveries")

        assert response.status_code == 404
