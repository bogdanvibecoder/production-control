"""Unit-тесты для BatchService."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models.batch import Batch, BatchStatus
from src.data.models.work_center import WorkCenter
from src.domain.exceptions import (
    BatchAlreadyExistsError,
    BatchNotFoundError,
    InvalidBatchStatusError,
)
from src.domain.services.batch_service import BatchService

# ============================================================================
# Создание партии
# ============================================================================


class TestCreateBatch:
    """Тесты создания партии."""

    async def test_create_success(self, session: AsyncSession, work_center: WorkCenter) -> None:
        """Партия успешно создаётся с корректными данными."""
        service = BatchService(session)

        batch = await service.create(
            number="B-NEW-001",
            work_center_id=work_center.id,
            shift_date=datetime(2026, 2, 15, tzinfo=UTC),
            shift_number=1,
            planned_quantity=Decimal("500.000"),
        )

        assert batch.id is not None
        assert batch.number == "B-NEW-001"
        assert batch.work_center_id == work_center.id
        assert batch.shift_number == 1
        assert batch.planned_quantity == Decimal("500.000")
        assert batch.actual_quantity == Decimal("0")
        assert batch.status == BatchStatus.PLANNED
        assert batch.started_at is None
        assert batch.completed_at is None

    async def test_create_duplicate_number_raises(
        self, session: AsyncSession, batch: Batch
    ) -> None:
        """Создание партии с существующим номером вызывает ошибку."""
        service = BatchService(session)

        with pytest.raises(BatchAlreadyExistsError):
            await service.create(
                number=batch.number,  # "B-2026-001" — уже существует
                work_center_id=batch.work_center_id,
                shift_date=datetime(2026, 3, 1, tzinfo=UTC),
                shift_number=2,
                planned_quantity=Decimal("100.000"),
            )


# ============================================================================
# Получение партии
# ============================================================================


class TestGetBatch:
    """Тесты получения партии."""

    async def test_get_by_id_success(self, session: AsyncSession, batch: Batch) -> None:
        """Партия находится по существующему ID."""
        service = BatchService(session)

        result = await service.get_by_id(batch.id)

        assert result.id == batch.id
        assert result.number == batch.number

    async def test_get_by_id_not_found(self, session: AsyncSession) -> None:
        """Несуществующий ID вызывает BatchNotFoundError."""
        service = BatchService(session)

        with pytest.raises(BatchNotFoundError):
            await service.get_by_id(99999)

    async def test_get_list_no_filters(self, session: AsyncSession, batch: Batch) -> None:
        """Список партий возвращается без фильтров."""
        service = BatchService(session)

        items, total = await service.get_list()

        assert total >= 1
        assert len(items) >= 1

    async def test_get_list_filter_by_status(self, session: AsyncSession, batch: Batch) -> None:
        """Фильтрация по статусу возвращает только нужные партии."""
        service = BatchService(session)

        items, _ = await service.get_list(status=BatchStatus.PLANNED)

        assert all(item.status == BatchStatus.PLANNED for item in items)

    async def test_get_list_filter_by_work_center(
        self, session: AsyncSession, batch: Batch, work_center: WorkCenter
    ) -> None:
        """Фильтрация по рабочему центру работает корректно."""
        service = BatchService(session)

        items, _ = await service.get_list(work_center_id=work_center.id)

        assert all(item.work_center_id == work_center.id for item in items)

    async def test_get_list_filter_by_date_range(self, session: AsyncSession, batch: Batch) -> None:
        """Фильтрация по диапазону дат работает корректно."""
        service = BatchService(session)

        items, _ = await service.get_list(
            date_from=datetime(2026, 2, 1, tzinfo=UTC),
            date_to=datetime(2026, 2, 28, tzinfo=UTC),
        )

        assert len(items) >= 1


# ============================================================================
# Обновление партии
# ============================================================================


class TestUpdateBatch:
    """Тесты обновления партии."""

    async def test_update_planned_quantity(self, session: AsyncSession, batch: Batch) -> None:
        """Обновление планового количества работает."""
        service = BatchService(session)

        updated = await service.update(
            batch.id,
            planned_quantity=Decimal("999.000"),
        )

        assert updated.planned_quantity == Decimal("999.000")

    async def test_update_actual_quantity(self, session: AsyncSession, batch: Batch) -> None:
        """Обновление фактического количества работает."""
        service = BatchService(session)

        updated = await service.update(
            batch.id,
            actual_quantity=Decimal("42.500"),
        )

        assert updated.actual_quantity == Decimal("42.500")

    async def test_update_no_data_returns_same(self, session: AsyncSession, batch: Batch) -> None:
        """Обновление без данных возвращает партию без изменений."""
        service = BatchService(session)

        result = await service.update(batch.id)

        assert result.id == batch.id

    async def test_update_not_found_raises(self, session: AsyncSession) -> None:
        """Обновление несуществующей партии вызывает ошибку."""
        service = BatchService(session)

        with pytest.raises(BatchNotFoundError):
            await service.update(
                99999,
                planned_quantity=Decimal("100.000"),
            )


# ============================================================================
# Удаление партии
# ============================================================================


class TestDeleteBatch:
    """Тесты удаления партии."""

    async def test_delete_success(self, session: AsyncSession, batch: Batch) -> None:
        """Существующая партия успешно удаляется."""
        service = BatchService(session)

        await service.delete(batch.id)

        with pytest.raises(BatchNotFoundError):
            await service.get_by_id(batch.id)

    async def test_delete_not_found_raises(self, session: AsyncSession) -> None:
        """Удаление несуществующей партии вызывает ошибку."""
        service = BatchService(session)

        with pytest.raises(BatchNotFoundError):
            await service.delete(99999)


# ============================================================================
# Переходы статусов
# ============================================================================


class TestBatchStatusTransitions:
    """Тесты переходов статусов партии — ключевая бизнес-логика."""

    # --- Допустимые переходы ---

    async def test_planned_to_in_progress(self, session: AsyncSession, batch: Batch) -> None:
        """planned → in_progress: устанавливается started_at."""
        service = BatchService(session)

        result = await service.change_status(batch.id, BatchStatus.IN_PROGRESS)

        assert result.status == BatchStatus.IN_PROGRESS
        assert result.started_at is not None

    async def test_planned_to_cancelled(self, session: AsyncSession, batch: Batch) -> None:
        """planned → cancelled: устанавливается completed_at."""
        service = BatchService(session)

        result = await service.change_status(batch.id, BatchStatus.CANCELLED)

        assert result.status == BatchStatus.CANCELLED
        assert result.completed_at is not None

    async def test_in_progress_to_completed(
        self, session: AsyncSession, batch_in_progress: Batch
    ) -> None:
        """in_progress → completed: устанавливается completed_at."""
        service = BatchService(session)

        result = await service.change_status(batch_in_progress.id, BatchStatus.COMPLETED)

        assert result.status == BatchStatus.COMPLETED
        assert result.completed_at is not None

    async def test_in_progress_to_cancelled(
        self, session: AsyncSession, batch_in_progress: Batch
    ) -> None:
        """in_progress → cancelled: устанавливается completed_at."""
        service = BatchService(session)

        result = await service.change_status(batch_in_progress.id, BatchStatus.CANCELLED)

        assert result.status == BatchStatus.CANCELLED
        assert result.completed_at is not None

    # --- Недопустимые переходы ---

    async def test_planned_to_completed_raises(self, session: AsyncSession, batch: Batch) -> None:
        """planned → completed: запрещено."""
        service = BatchService(session)

        with pytest.raises(InvalidBatchStatusError):
            await service.change_status(batch.id, BatchStatus.COMPLETED)

    async def test_completed_to_any_raises(
        self, session: AsyncSession, batch_in_progress: Batch
    ) -> None:
        """completed → любой: запрещено (терминальный статус)."""
        service = BatchService(session)

        # Сначала завершаем
        await service.change_status(batch_in_progress.id, BatchStatus.COMPLETED)

        # Пытаемся изменить
        with pytest.raises(InvalidBatchStatusError):
            await service.change_status(batch_in_progress.id, BatchStatus.IN_PROGRESS)

    async def test_cancelled_to_any_raises(self, session: AsyncSession, batch: Batch) -> None:
        """cancelled → любой: запрещено (терминальный статус)."""
        service = BatchService(session)

        # Сначала отменяем
        await service.change_status(batch.id, BatchStatus.CANCELLED)

        # Пытаемся изменить
        with pytest.raises(InvalidBatchStatusError):
            await service.change_status(batch.id, BatchStatus.PLANNED)

    async def test_change_status_not_found_raises(
        self,
        session: AsyncSession,
    ) -> None:
        """Смена статуса несуществующей партии вызывает ошибку."""
        service = BatchService(session)

        with pytest.raises(BatchNotFoundError):
            await service.change_status(99999, BatchStatus.IN_PROGRESS)
