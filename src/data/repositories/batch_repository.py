from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.batch import Batch, BatchStatus
from .base_repository import BaseRepository


class BatchRepository(BaseRepository[Batch]):
    """
    Репозиторий для работы с партиями (сменными заданиями).
    Наследует базовые CRUD-операции и добавляет специфичные методы.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Batch)

    async def get_by_number(self, number: str) -> Batch | None:
        """Получить партию по номеру."""
        stmt = select(Batch).where(Batch.number == number)
        result = await self._session.scalar(stmt)
        return result

    async def get_by_work_center(
        self,
        work_center_id: int,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Batch]:
        """Получить партии по рабочему центру."""
        stmt = (
            select(Batch)
            .where(Batch.work_center_id == work_center_id)
            .order_by(Batch.shift_date.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return result.all()

    async def get_by_status(
        self,
        status: BatchStatus,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Batch]:
        """Получить партии по статусу."""
        stmt = (
            select(Batch)
            .where(Batch.status == status)
            .order_by(Batch.shift_date.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return result.all()

    async def get_by_shift(
        self,
        shift_date: datetime,
        shift_number: int,
        *,
        work_center_id: int | None = None,
    ) -> Sequence[Batch]:
        """
        Получить партии по смене.
        Args:
            shift_date: Дата смены
            shift_number: Номер смены (1, 2, 3)
            work_center_id: Опционально - фильтр по рабочему центру
        """
        conditions = [
            Batch.shift_date == shift_date,
            Batch.shift_number == shift_number,
        ]
        if work_center_id is not None:
            conditions.append(Batch.work_center_id == work_center_id)

        stmt = select(Batch).where(and_(*conditions))
        result = await self._session.scalars(stmt)
        return result.all()

    async def get_by_date_range(
        self,
        date_from: datetime,
        date_to: datetime,
        *,
        status: BatchStatus | None = None,
        work_center_id: int | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Batch]:
        """
        Получить партии за период.
        Args:
            date_from: Начало периода
            date_to: Конец периода
            status: Опционально - фильтр по статусу
            work_center_id: Опционально - фильтр по рабочему центру
        """
        conditions = [
            Batch.shift_date >= date_from,
            Batch.shift_date <= date_to,
        ]
        if status is not None:
            conditions.append(Batch.status == status)
        if work_center_id is not None:
            conditions.append(Batch.work_center_id == work_center_id)

        stmt = (
            select(Batch)
            .where(and_(*conditions))
            .order_by(Batch.shift_date.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return result.all()
