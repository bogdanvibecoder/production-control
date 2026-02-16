"""Integration-тесты для API аналитики (/api/v1/analytics)."""

from httpx import AsyncClient

from src.data.models.batch import Batch
from src.data.models.product import Product
from src.data.models.work_center import WorkCenter

API = "/api/v1/analytics"


# ============================================================================
# GET /analytics/batches/summary — сводка
# ============================================================================


class TestBatchSummaryAPI:
    """Тесты сводки по партиям."""

    async def test_summary_200(self, client: AsyncClient, batch: Batch) -> None:
        """Сводка → 200 + корректная структура."""
        response = await client.get(f"{API}/batches/summary")

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "by_status" in data
        assert data["total"] >= 1
        assert "planned" in data["by_status"]
        assert "in_progress" in data["by_status"]
        assert "completed" in data["by_status"]
        assert "cancelled" in data["by_status"]

    async def test_summary_empty_200(self, client: AsyncClient) -> None:
        """Сводка при пустой БД → 200 + нули."""
        response = await client.get(f"{API}/batches/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    async def test_summary_counts(
        self,
        client: AsyncClient,
        batch: Batch,
        batch_in_progress: Batch,
    ) -> None:
        """Сводка корректно считает: 1 planned + 1 in_progress."""
        response = await client.get(f"{API}/batches/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["by_status"]["planned"] == 1
        assert data["by_status"]["in_progress"] == 1


# ============================================================================
# GET /analytics/batches/{id} — детали партии
# ============================================================================


class TestBatchDetailsAPI:
    """Тесты детальной аналитики партии."""

    async def test_details_200(self, client: AsyncClient, batch: Batch) -> None:
        """Детали партии → 200 + все поля."""
        response = await client.get(f"{API}/batches/{batch.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["batch_id"] == batch.id
        assert data["batch_number"] == batch.number
        assert data["status"] == "planned"
        assert "planned_quantity" in data
        assert "actual_quantity" in data
        assert "completion_percent" in data
        assert "total_products" in data
        assert "products_by_status" in data

    async def test_details_with_products(
        self,
        client: AsyncClient,
        batch: Batch,
        product: Product,
    ) -> None:
        """Детали партии с продукцией: total_products >= 1."""
        response = await client.get(f"{API}/batches/{batch.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["total_products"] >= 1
        assert data["products_by_status"]["produced"] >= 1

    async def test_details_not_found_404(self, client: AsyncClient) -> None:
        """Несуществующая партия → 404."""
        response = await client.get(f"{API}/batches/99999")

        assert response.status_code == 404


# ============================================================================
# GET /analytics/production-report — отчёт за период
# ============================================================================


class TestProductionReportAPI:
    """Тесты производственного отчёта."""

    async def test_report_200(self, client: AsyncClient, batch: Batch) -> None:
        """Отчёт за период → 200 + корректная структура."""
        response = await client.get(
            f"{API}/production-report",
            params={
                "date_from": "2026-02-01T00:00:00Z",
                "date_to": "2026-02-28T00:00:00Z",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_batches" in data
        assert "batches_by_status" in data
        assert "total_planned" in data
        assert "total_actual" in data
        assert "completion_percent" in data
        assert data["total_batches"] >= 1

    async def test_report_with_work_center(
        self,
        client: AsyncClient,
        batch: Batch,
        work_center: WorkCenter,
    ) -> None:
        """Отчёт с фильтром по рабочему центру."""
        response = await client.get(
            f"{API}/production-report",
            params={
                "date_from": "2026-02-01T00:00:00Z",
                "date_to": "2026-02-28T00:00:00Z",
                "work_center_id": work_center.id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["work_center_id"] == work_center.id
        assert data["total_batches"] >= 1

    async def test_report_empty_period(self, client: AsyncClient, batch: Batch) -> None:
        """Отчёт за пустой период → 200 + нули."""
        response = await client.get(
            f"{API}/production-report",
            params={
                "date_from": "2020-01-01T00:00:00Z",
                "date_to": "2020-01-31T00:00:00Z",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_batches"] == 0

    async def test_report_missing_dates_422(self, client: AsyncClient) -> None:
        """Отсутствие обязательных дат → 422."""
        response = await client.get(f"{API}/production-report")

        assert response.status_code == 422
