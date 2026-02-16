"""Integration-тесты для API партий (/api/v1/batches)."""

from decimal import Decimal

from httpx import AsyncClient

from src.data.models.batch import Batch
from src.data.models.work_center import WorkCenter

API = "/api/v1/batches"


# ============================================================================
# POST /batches — создание
# ============================================================================


class TestCreateBatchAPI:
    """Тесты создания партии через API."""

    async def test_create_201(self, client: AsyncClient, work_center: WorkCenter) -> None:
        """Успешное создание → 201 + корректный JSON."""
        response = await client.post(
            API,
            json={
                "number": "B-API-001",
                "work_center_id": work_center.id,
                "shift_date": "2026-02-15T00:00:00Z",
                "shift_number": 1,
                "planned_quantity": "100.000",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["number"] == "B-API-001"
        assert data["status"] == "planned"
        assert data["work_center_id"] == work_center.id
        assert Decimal(data["planned_quantity"]) == Decimal("100.000")
        assert data["started_at"] is None
        assert data["completed_at"] is None
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    async def test_create_duplicate_400(self, client: AsyncClient, batch: Batch) -> None:
        """Дубликат номера → 400."""
        response = await client.post(
            API,
            json={
                "number": batch.number,
                "work_center_id": batch.work_center_id,
                "shift_date": "2026-03-01T00:00:00Z",
                "shift_number": 2,
                "planned_quantity": "50.000",
            },
        )

        assert response.status_code == 400

    async def test_create_invalid_shift_number_422(
        self, client: AsyncClient, work_center: WorkCenter
    ) -> None:
        """Невалидный номер смены (4) → 422."""
        response = await client.post(
            API,
            json={
                "number": "B-INVALID",
                "work_center_id": work_center.id,
                "shift_date": "2026-02-15T00:00:00Z",
                "shift_number": 4,
                "planned_quantity": "100.000",
            },
        )

        assert response.status_code == 422

    async def test_create_negative_quantity_422(
        self, client: AsyncClient, work_center: WorkCenter
    ) -> None:
        """Отрицательное количество → 422."""
        response = await client.post(
            API,
            json={
                "number": "B-NEG",
                "work_center_id": work_center.id,
                "shift_date": "2026-02-15T00:00:00Z",
                "shift_number": 1,
                "planned_quantity": "-10.000",
            },
        )

        assert response.status_code == 422


# ============================================================================
# GET /batches — список
# ============================================================================


class TestGetBatchesAPI:
    """Тесты получения списка партий."""

    async def test_get_list_200(self, client: AsyncClient, batch: Batch) -> None:
        """Список партий → 200 + PaginatedResponse."""
        response = await client.get(API)

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "offset" in data
        assert "limit" in data
        assert data["total"] >= 1
        assert len(data["items"]) >= 1

    async def test_get_list_with_pagination(self, client: AsyncClient, batch: Batch) -> None:
        """Пагинация: offset и limit работают."""
        response = await client.get(API, params={"offset": 0, "limit": 1})

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 1

    async def test_get_list_filter_by_status(self, client: AsyncClient, batch: Batch) -> None:
        """Фильтр по статусу работает."""
        response = await client.get(API, params={"status": "planned"})

        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["status"] == "planned"


# ============================================================================
# GET /batches/{id} — получение по ID
# ============================================================================


class TestGetBatchByIdAPI:
    """Тесты получения партии по ID."""

    async def test_get_by_id_200(self, client: AsyncClient, batch: Batch) -> None:
        """Существующий ID → 200 + BatchRead."""
        response = await client.get(f"{API}/{batch.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == batch.id
        assert data["number"] == batch.number

    async def test_get_by_id_404(self, client: AsyncClient) -> None:
        """Несуществующий ID → 404."""
        response = await client.get(f"{API}/99999")

        assert response.status_code == 404


# ============================================================================
# PATCH /batches/{id} — обновление
# ============================================================================


class TestUpdateBatchAPI:
    """Тесты обновления партии через API."""

    async def test_update_fields_200(self, client: AsyncClient, batch: Batch) -> None:
        """Обновление полей → 200 + обновлённые данные."""
        response = await client.patch(
            f"{API}/{batch.id}",
            json={"planned_quantity": "999.000"},
        )

        assert response.status_code == 200
        data = response.json()
        assert Decimal(data["planned_quantity"]) == Decimal("999.000")

    async def test_update_status_200(self, client: AsyncClient, batch: Batch) -> None:
        """Смена статуса planned → in_progress → 200."""
        response = await client.patch(
            f"{API}/{batch.id}",
            json={"status": "in_progress"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"
        assert data["started_at"] is not None

    async def test_update_invalid_status_400(self, client: AsyncClient, batch: Batch) -> None:
        """Невалидный переход planned → completed → 400."""
        response = await client.patch(
            f"{API}/{batch.id}",
            json={"status": "completed"},
        )

        assert response.status_code == 400

    async def test_update_not_found_404(self, client: AsyncClient) -> None:
        """Обновление несуществующей партии → 404."""
        response = await client.patch(
            f"{API}/99999",
            json={"planned_quantity": "100.000"},
        )

        assert response.status_code == 404

    async def test_full_lifecycle(self, client: AsyncClient, batch: Batch) -> None:
        """Полный жизненный цикл: planned → in_progress → completed."""
        # planned → in_progress
        r1 = await client.patch(
            f"{API}/{batch.id}",
            json={"status": "in_progress"},
        )
        assert r1.status_code == 200
        assert r1.json()["status"] == "in_progress"

        # in_progress → completed
        r2 = await client.patch(
            f"{API}/{batch.id}",
            json={"status": "completed"},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "completed"
        assert r2.json()["completed_at"] is not None


# ============================================================================
# DELETE /batches/{id} — удаление
# ============================================================================


class TestDeleteBatchAPI:
    """Тесты удаления партии через API."""

    async def test_delete_204(self, client: AsyncClient, batch: Batch) -> None:
        """Успешное удаление → 204."""
        response = await client.delete(f"{API}/{batch.id}")

        assert response.status_code == 204

        # Проверяем, что партия удалена
        check = await client.get(f"{API}/{batch.id}")
        assert check.status_code == 404

    async def test_delete_not_found_404(self, client: AsyncClient) -> None:
        """Удаление несуществующей партии → 404."""
        response = await client.delete(f"{API}/99999")

        assert response.status_code == 404
