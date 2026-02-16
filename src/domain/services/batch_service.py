from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...data.models.batch import Batch, BatchStatus
from ...data.repositories.batch_repository import BatchRepository
from ..exceptions import (
    BatchAlreadyExistsError,
    BatchNotFoundError,
    InvalidBatchStatusError,
)

ALLOWED_STATUS_TRANSITIONS: dict[BatchStatus, set[BatchStatus]] = {
    BatchStatus.PLANNED: {BatchStatus.IN_PROGRESS, BatchStatus.CANCELLED},
    BatchStatus.IN_PROGRESS: {BatchStatus.COMPLETED, BatchStatus.CANCELLED},
    BatchStatus.COMPLETED: set(),
    BatchStatus.CANCELLED: set(),
}


class BatchService:
    """Сервис бизнес-логики для работы с партиями."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BatchRepository(session)

    async def get_by_id(self, batch_id: int) -> Batch:
        """Получить партию по ID."""
        batch = await self._repo.get_by_id(batch_id)
        if batch is None:
            raise BatchNotFoundError(details={"batch_id": batch_id})
        return batch

    async def get_list(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        status: BatchStatus | None = None,
        work_center_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> tuple[Sequence[Batch], int]:
        """Получить список партий с фильтрацией и пагинацией."""
        if date_from and date_to:
            items = await self._repo.get_by_date_range(
                date_from,
                date_to,
                status=status,
                work_center_id=work_center_id,
                offset=offset,
                limit=limit,
            )
        elif status is not None:
            items = await self._repo.get_by_status(
                status,
                offset=offset,
                limit=limit,
            )
        elif work_center_id is not None:
            items = await self._repo.get_by_work_center(
                work_center_id,
                offset=offset,
                limit=limit,
            )
        else:
            items = await self._repo.get_all(offset=offset, limit=limit)

        total = await self._repo.count()
        return items, total

    async def create(
        self,
        *,
        number: str,
        work_center_id: int,
        shift_date: datetime,
        shift_number: int,
        planned_quantity: Decimal,
    ) -> Batch:
        """Создать новую партию."""
        existing = await self._repo.get_by_number(number)
        if existing is not None:
            raise BatchAlreadyExistsError(details={"number": number})

        batch = await self._repo.create(
            number=number,
            work_center_id=work_center_id,
            shift_date=shift_date,
            shift_number=shift_number,
            planned_quantity=planned_quantity,
        )
        await self._session.commit()
        return batch

    async def update(
        self,
        batch_id: int,
        *,
        shift_date: datetime | None = None,
        shift_number: int | None = None,
        planned_quantity: Decimal | None = None,
        actual_quantity: Decimal | None = None,
    ) -> Batch:
        """Обновить данные партии (без смены статуса)."""
        data: dict[str, Any] = {}
        if shift_date is not None:
            data["shift_date"] = shift_date
        if shift_number is not None:
            data["shift_number"] = shift_number
        if planned_quantity is not None:
            data["planned_quantity"] = planned_quantity
        if actual_quantity is not None:
            data["actual_quantity"] = actual_quantity

        if not data:
            return await self.get_by_id(batch_id)

        batch = await self._repo.update(batch_id, **data)
        if batch is None:
            raise BatchNotFoundError(details={"batch_id": batch_id})
        await self._session.commit()
        return batch

    async def delete(self, batch_id: int) -> None:
        """Удалить партию."""
        deleted = await self._repo.delete(batch_id)
        if not deleted:
            raise BatchNotFoundError(details={"batch_id": batch_id})
        await self._session.commit()

    async def change_status(
        self,
        batch_id: int,
        new_status: BatchStatus,
    ) -> Batch:
        """Сменить статус партии с валидацией перехода.

        Проверяет допустимость перехода по матрице ALLOWED_STATUS_TRANSITIONS:
        - planned → in_progress, cancelled
        - in_progress → completed, cancelled
        - completed → (терминальный)
        - cancelled → (терминальный)

        При переходе в IN_PROGRESS проставляется started_at.
        При переходе в COMPLETED или CANCELLED проставляется completed_at.

        Args:
            batch_id: ID партии для смены статуса.
            new_status: Целевой статус.

        Returns:
            Обновлённая партия.

        Raises:
            BatchNotFoundError: Партия не найдена.
            InvalidBatchStatusError: Переход недопустим.
        """
        batch = await self.get_by_id(batch_id)

        allowed = ALLOWED_STATUS_TRANSITIONS.get(batch.status, set())
        if new_status not in allowed:
            raise InvalidBatchStatusError(
                details={
                    "current_status": batch.status.value,
                    "new_status": new_status.value,
                    "allowed_transitions": [s.value for s in allowed],
                },
            )

        update_data: dict[str, Any] = {"status": new_status}
        now = datetime.now(UTC)

        if new_status == BatchStatus.IN_PROGRESS:
            update_data["started_at"] = now
        elif new_status in (BatchStatus.COMPLETED, BatchStatus.CANCELLED):
            update_data["completed_at"] = now

        updated = await self._repo.update(batch_id, **update_data)
        if updated is None:
            raise BatchNotFoundError(details={"batch_id": batch_id})
        await self._session.commit()
        return updated
