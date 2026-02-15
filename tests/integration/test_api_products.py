"""Integration-тесты для API продукции (/api/v1/products)."""

from httpx import AsyncClient

from src.data.models.batch import Batch
from src.data.models.product import Product

API = "/api/v1/products"


# ============================================================================
# POST /products — создание
# ============================================================================


class TestCreateProductAPI:
    """Тесты создания продукции через API."""

    async def test_create_201(self, client: AsyncClient, batch: Batch) -> None:
        """Успешное создание → 201 + корректный JSON."""
        response = await client.post(
            API,
            json={
                "code": "API-PRD-001",
                "batch_id": batch.id,
                "product_type": "bottle",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["code"] == "API-PRD-001"
        assert data["batch_id"] == batch.id
        assert data["product_type"] == "bottle"
        assert data["status"] == "produced"
        assert "id" in data
        assert "created_at" in data

    async def test_create_with_extra_data(self, client: AsyncClient, batch: Batch) -> None:
        """Создание с дополнительными данными."""
        response = await client.post(
            API,
            json={
                "code": "API-PRD-002",
                "batch_id": batch.id,
                "product_type": "box",
                "extra_data": '{"weight": 1.5}',
            },
        )

        assert response.status_code == 201
        assert response.json()["extra_data"] == '{"weight": 1.5}'

    async def test_create_duplicate_code_400(self, client: AsyncClient, product: Product) -> None:
        """Дубликат кода → 400."""
        response = await client.post(
            API,
            json={
                "code": product.code,
                "batch_id": product.batch_id,
                "product_type": "bottle",
            },
        )

        assert response.status_code == 400

    async def test_create_empty_code_422(self, client: AsyncClient, batch: Batch) -> None:
        """Пустой код → 422 (min_length=1)."""
        response = await client.post(
            API,
            json={
                "code": "",
                "batch_id": batch.id,
                "product_type": "bottle",
            },
        )

        assert response.status_code == 422

    async def test_create_missing_product_type_422(self, client: AsyncClient, batch: Batch) -> None:
        """Отсутствует обязательное поле product_type → 422."""
        response = await client.post(
            API,
            json={
                "code": "API-PRD-003",
                "batch_id": batch.id,
            },
        )

        assert response.status_code == 422


# ============================================================================
# GET /products — список
# ============================================================================


class TestGetProductsAPI:
    """Тесты получения списка продукции."""

    async def test_get_list_200(self, client: AsyncClient, product: Product) -> None:
        """Список продукции → 200 + PaginatedResponse."""
        response = await client.get(API)

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    async def test_get_list_filter_by_batch(
        self, client: AsyncClient, product: Product, batch: Batch
    ) -> None:
        """Фильтр по batch_id работает."""
        response = await client.get(API, params={"batch_id": batch.id})

        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["batch_id"] == batch.id

    async def test_get_list_filter_by_status(self, client: AsyncClient, product: Product) -> None:
        """Фильтр по статусу работает."""
        response = await client.get(API, params={"status": "produced"})

        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["status"] == "produced"

    async def test_get_list_pagination(self, client: AsyncClient, product: Product) -> None:
        """Пагинация работает."""
        response = await client.get(API, params={"offset": 0, "limit": 1})

        assert response.status_code == 200
        assert len(response.json()["items"]) <= 1


# ============================================================================
# GET /products/{id} — получение по ID
# ============================================================================


class TestGetProductByIdAPI:
    """Тесты получения продукции по ID."""

    async def test_get_by_id_200(self, client: AsyncClient, product: Product) -> None:
        """Существующий ID → 200."""
        response = await client.get(f"{API}/{product.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == product.id
        assert data["code"] == product.code

    async def test_get_by_id_404(self, client: AsyncClient) -> None:
        """Несуществующий ID → 404."""
        response = await client.get(f"{API}/99999")

        assert response.status_code == 404


# ============================================================================
# PATCH /products/{id} — обновление
# ============================================================================


class TestUpdateProductAPI:
    """Тесты обновления продукции через API."""

    async def test_update_fields_200(self, client: AsyncClient, product: Product) -> None:
        """Обновление полей → 200."""
        response = await client.patch(
            f"{API}/{product.id}",
            json={"product_type": "pallet", "extra_data": '{"line": 5}'},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["product_type"] == "pallet"
        assert data["extra_data"] == '{"line": 5}'

    async def test_update_status_200(self, client: AsyncClient, product: Product) -> None:
        """Смена статуса produced → aggregated → 200."""
        response = await client.patch(
            f"{API}/{product.id}",
            json={"status": "aggregated"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "aggregated"

    async def test_update_invalid_status_400(self, client: AsyncClient, product: Product) -> None:
        """Невалидный переход produced → shipped → 400."""
        response = await client.patch(
            f"{API}/{product.id}",
            json={"status": "shipped"},
        )

        assert response.status_code == 400

    async def test_update_not_found_404(self, client: AsyncClient) -> None:
        """Обновление несуществующей продукции → 404."""
        response = await client.patch(
            f"{API}/99999",
            json={"product_type": "box"},
        )

        assert response.status_code == 404

    async def test_full_lifecycle(self, client: AsyncClient, product: Product) -> None:
        """Полный цикл: produced → aggregated → shipped."""
        # produced → aggregated
        r1 = await client.patch(
            f"{API}/{product.id}",
            json={"status": "aggregated"},
        )
        assert r1.status_code == 200
        assert r1.json()["status"] == "aggregated"

        # aggregated → shipped
        r2 = await client.patch(
            f"{API}/{product.id}",
            json={"status": "shipped"},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "shipped"


# ============================================================================
# DELETE /products/{id} — удаление
# ============================================================================


class TestDeleteProductAPI:
    """Тесты удаления продукции через API."""

    async def test_delete_204(self, client: AsyncClient, product: Product) -> None:
        """Успешное удаление → 204."""
        response = await client.delete(f"{API}/{product.id}")
        assert response.status_code == 204

        # Проверяем, что удалено
        check = await client.get(f"{API}/{product.id}")
        assert check.status_code == 404

    async def test_delete_not_found_404(self, client: AsyncClient) -> None:
        """Удаление несуществующей продукции → 404."""
        response = await client.delete(f"{API}/99999")
        assert response.status_code == 404


# ============================================================================
# POST /products/bulk-status — массовое обновление
# ============================================================================


class TestBulkStatusAPI:
    """Тесты массового обновления статуса."""

    async def test_bulk_update_200(self, client: AsyncClient, batch: Batch) -> None:
        """Массовое обновление → 200 + SuccessResponse."""
        # Создаём 3 единицы
        codes = []
        for i in range(3):
            r = await client.post(
                API,
                json={
                    "code": f"BULK-API-{i:03d}",
                    "batch_id": batch.id,
                    "product_type": "bottle",
                },
            )
            assert r.status_code == 201
            codes.append(r.json()["code"])

        # Массовый перевод produced → aggregated
        response = await client.post(
            f"{API}/bulk-status",
            json={"codes": codes, "new_status": "aggregated"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "3" in data["message"]

    async def test_bulk_update_not_found_404(self, client: AsyncClient) -> None:
        """Несуществующие коды → 404."""
        response = await client.post(
            f"{API}/bulk-status",
            json={
                "codes": ["FAKE-001", "FAKE-002"],
                "new_status": "aggregated",
            },
        )

        assert response.status_code == 404

    async def test_bulk_update_invalid_transition_400(
        self, client: AsyncClient, product: Product
    ) -> None:
        """Невалидный переход produced → shipped → 400."""
        response = await client.post(
            f"{API}/bulk-status",
            json={
                "codes": [product.code],
                "new_status": "shipped",
            },
        )

        assert response.status_code == 400

    async def test_bulk_update_empty_codes_422(self, client: AsyncClient) -> None:
        """Пустой список кодов → 422 (min_length=1)."""
        response = await client.post(
            f"{API}/bulk-status",
            json={"codes": [], "new_status": "aggregated"},
        )

        assert response.status_code == 422
