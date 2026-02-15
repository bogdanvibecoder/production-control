"""Unit-тесты для AnalyticsService."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models.batch import Batch, BatchStatus
from src.data.models.product import Product
from src.data.models.work_center import WorkCenter
from src.domain.exceptions import BatchNotFoundError
from src.domain.services.analytics_service import AnalyticsService

# ============================================================================
# Сводка по партиям
# ============================================================================


class TestBatchSummary:
    """Тесты общей сводки по партиям."""

    async def test_summary_empty_db(self, session: AsyncSession) -> None:
        """Сводка при пустой БД: total=0, все статусы по нулям."""
        service = AnalyticsService(session)

        result = await service.get_batch_summary()

        assert result["total"] == 0
        assert result["by_status"]["planned"] == 0
        assert result["by_status"]["in_progress"] == 0
        assert result["by_status"]["completed"] == 0
        assert result["by_status"]["cancelled"] == 0

    async def test_summary_with_batches(
        self,
        session: AsyncSession,
        batch: Batch,
        batch_in_progress: Batch,
    ) -> None:
        """Сводка корректно считает партии по статусам."""
        service = AnalyticsService(session)

        result = await service.get_batch_summary()

        assert result["total"] == 2
        assert result["by_status"]["planned"] == 1
        assert result["by_status"]["in_progress"] == 1

    async def test_summary_all_statuses(
        self, session: AsyncSession, work_center: WorkCenter
    ) -> None:
        """Сводка учитывает все 4 статуса."""
        # Создаём по одной партии каждого статуса
        for i, status in enumerate(BatchStatus):
            b = Batch(
                number=f"SUMM-{i:03d}",
                work_center_id=work_center.id,
                shift_date=datetime(2026, 2, 15, tzinfo=UTC),
                shift_number=1,
                status=status,
                planned_quantity=Decimal("100.000"),
                actual_quantity=Decimal("0.000"),
            )
            session.add(b)
        await session.flush()

        service = AnalyticsService(session)
        result = await service.get_batch_summary()

        assert result["total"] == 4
        assert result["by_status"]["planned"] == 1
        assert result["by_status"]["in_progress"] == 1
        assert result["by_status"]["completed"] == 1
        assert result["by_status"]["cancelled"] == 1


# ============================================================================
# Детальная аналитика партии
# ============================================================================


class TestBatchDetails:
    """Тесты детальной аналитики по одной партии."""

    async def test_details_basic(self, session: AsyncSession, batch: Batch) -> None:
        """Детали партии возвращают корректные поля."""
        service = AnalyticsService(session)

        result = await service.get_batch_details(batch.id)

        assert result["batch_id"] == batch.id
        assert result["batch_number"] == batch.number
        assert result["status"] == "planned"
        assert result["planned_quantity"] == Decimal("100.000")
        assert result["actual_quantity"] == Decimal("0")

    async def test_details_with_products(
        self, session: AsyncSession, batch: Batch, product: Product
    ) -> None:
        """Детали партии считают продукцию по статусам."""
        service = AnalyticsService(session)

        result = await service.get_batch_details(batch.id)

        assert result["total_products"] >= 1
        assert result["products_by_status"]["produced"] >= 1

    async def test_details_completion_percent(
        self, session: AsyncSession, work_center: WorkCenter
    ) -> None:
        """Процент выполнения рассчитывается корректно."""
        # Партия: план 200, факт 150 → 75%
        b = Batch(
            number="PERC-001",
            work_center_id=work_center.id,
            shift_date=datetime(2026, 2, 15, tzinfo=UTC),
            shift_number=1,
            status=BatchStatus.IN_PROGRESS,
            planned_quantity=Decimal("200.000"),
            actual_quantity=Decimal("150.000"),
        )
        session.add(b)
        await session.flush()
        await session.refresh(b)

        service = AnalyticsService(session)
        result = await service.get_batch_details(b.id)

        assert result["completion_percent"] == Decimal("75.00")

    async def test_details_zero_planned(
        self, session: AsyncSession, work_center: WorkCenter
    ) -> None:
        """Процент = 0 если план = 0 (деление на ноль)."""
        b = Batch(
            number="ZERO-001",
            work_center_id=work_center.id,
            shift_date=datetime(2026, 2, 15, tzinfo=UTC),
            shift_number=1,
            status=BatchStatus.PLANNED,
            planned_quantity=Decimal("0.000"),
            actual_quantity=Decimal("0.000"),
        )
        session.add(b)
        await session.flush()
        await session.refresh(b)

        service = AnalyticsService(session)
        result = await service.get_batch_details(b.id)

        assert result["completion_percent"] == Decimal("0")

    async def test_details_not_found(self, session: AsyncSession) -> None:
        """Детали несуществующей партии вызывают ошибку."""
        service = AnalyticsService(session)

        with pytest.raises(BatchNotFoundError):
            await service.get_batch_details(99999)


# ============================================================================
# Производственный отчёт за период
# ============================================================================


class TestProductionReport:
    """Тесты отчёта по производству за период."""

    async def test_report_empty_period(self, session: AsyncSession) -> None:
        """Отчёт за пустой период: нули."""
        service = AnalyticsService(session)

        result = await service.get_production_report(
            date_from=datetime(2020, 1, 1, tzinfo=UTC),
            date_to=datetime(2020, 1, 31, tzinfo=UTC),
        )

        assert result["total_batches"] == 0
        assert result["total_planned"] == Decimal("0")
        assert result["total_actual"] == Decimal("0")
        assert result["completion_percent"] == Decimal("0")

    async def test_report_with_data(
        self,
        session: AsyncSession,
        batch: Batch,
        batch_in_progress: Batch,
    ) -> None:
        """Отчёт за период с данными корректно агрегирует."""
        service = AnalyticsService(session)

        result = await service.get_production_report(
            date_from=datetime(2026, 2, 1, tzinfo=UTC),
            date_to=datetime(2026, 2, 28, tzinfo=UTC),
        )

        # batch (planned, 100) + batch_in_progress (in_progress, 200)
        assert result["total_batches"] == 2
        assert result["total_planned"] == Decimal("300.000")
        assert result["total_actual"] == Decimal("50.000")
        assert result["batches_by_status"]["planned"] == 1
        assert result["batches_by_status"]["in_progress"] == 1

    async def test_report_filter_by_work_center(
        self,
        session: AsyncSession,
        batch: Batch,
        work_center: WorkCenter,
    ) -> None:
        """Фильтр по рабочему центру работает корректно."""
        service = AnalyticsService(session)

        result = await service.get_production_report(
            date_from=datetime(2026, 2, 1, tzinfo=UTC),
            date_to=datetime(2026, 2, 28, tzinfo=UTC),
            work_center_id=work_center.id,
        )

        assert result["work_center_id"] == work_center.id
        assert result["total_batches"] >= 1

    async def test_report_filter_nonexistent_work_center(
        self, session: AsyncSession, batch: Batch
    ) -> None:
        """Фильтр по несуществующему рабочему центру: нули."""
        service = AnalyticsService(session)

        result = await service.get_production_report(
            date_from=datetime(2026, 2, 1, tzinfo=UTC),
            date_to=datetime(2026, 2, 28, tzinfo=UTC),
            work_center_id=99999,
        )

        assert result["total_batches"] == 0

    async def test_report_date_boundaries(
        self,
        session: AsyncSession,
        batch: Batch,
    ) -> None:
        """Партия на границе периода включается в отчёт."""
        service = AnalyticsService(session)

        # batch.shift_date = 2026-02-15 — точная граница
        result = await service.get_production_report(
            date_from=datetime(2026, 2, 15, tzinfo=UTC),
            date_to=datetime(2026, 2, 15, tzinfo=UTC),
        )

        assert result["total_batches"] >= 1
