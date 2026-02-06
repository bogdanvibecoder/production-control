from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...data.models.batch import Batch, BatchStatus
from ...data.models.product import Product, ProductStatus
from ...data.repositories.batch_repository import BatchRepository
from ..exceptions import BatchNotFoundError


class AnalyticsService:
    """Сервис аналитики производственных данных."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._batch_repo = BatchRepository(session)

    async def get_batch_summary(self) -> dict[str, Any]:
        """Общая сводка по партиям: количество по статусам."""
        stmt = select(
            Batch.status,
            func.count().label("cnt"),
        ).group_by(Batch.status)
        result = await self._session.execute(stmt)
        rows = result.all()

        status_counts: dict[str, int] = {s.value: 0 for s in BatchStatus}
        for row in rows:
            status_counts[row.status.value] = row.cnt

        total = sum(status_counts.values())

        return {
            "total": total,
            "by_status": status_counts,
        }

    async def get_batch_details(self, batch_id: int) -> dict[str, Any]:
        """Детальная аналитика по конкретной партии."""
        batch = await self._batch_repo.get_by_id(batch_id)
        if batch is None:
            raise BatchNotFoundError(details={"batch_id": batch_id})

        stmt = (
            select(
                Product.status,
                func.count().label("cnt"),
            )
            .where(Product.batch_id == batch_id)
            .group_by(Product.status)
        )
        result = await self._session.execute(stmt)
        rows = result.all()

        product_counts: dict[str, int] = {s.value: 0 for s in ProductStatus}
        for row in rows:
            product_counts[row.status.value] = row.cnt

        total_products = sum(product_counts.values())

        completion_percent = Decimal("0")
        if batch.planned_quantity > 0:
            completion_percent = (batch.actual_quantity / batch.planned_quantity * 100).quantize(
                Decimal("0.01")
            )

        return {
            "batch_id": batch_id,
            "batch_number": batch.number,
            "status": batch.status.value,
            "planned_quantity": batch.planned_quantity,
            "actual_quantity": batch.actual_quantity,
            "completion_percent": completion_percent,
            "total_products": total_products,
            "products_by_status": product_counts,
        }

    async def get_production_report(
        self,
        date_from: datetime,
        date_to: datetime,
        *,
        work_center_id: int | None = None,
    ) -> dict[str, Any]:
        """Отчёт по производству за период."""
        conditions = [
            Batch.shift_date >= date_from,
            Batch.shift_date <= date_to,
        ]
        if work_center_id is not None:
            conditions.append(Batch.work_center_id == work_center_id)

        stmt = (
            select(
                Batch.status,
                func.count().label("cnt"),
                func.coalesce(func.sum(Batch.planned_quantity), 0).label(
                    "planned",
                ),
                func.coalesce(func.sum(Batch.actual_quantity), 0).label(
                    "actual",
                ),
            )
            .where(and_(*conditions))
            .group_by(Batch.status)
        )
        result = await self._session.execute(stmt)
        rows = result.all()

        status_counts: dict[str, int] = {s.value: 0 for s in BatchStatus}
        total_planned = Decimal("0")
        total_actual = Decimal("0")
        total_batches = 0

        for row in rows:
            status_counts[row.status.value] = row.cnt
            total_batches += row.cnt
            total_planned += row.planned
            total_actual += row.actual

        completion_percent = Decimal("0")
        if total_planned > 0:
            completion_percent = (total_actual / total_planned * 100).quantize(Decimal("0.01"))

        return {
            "date_from": date_from,
            "date_to": date_to,
            "work_center_id": work_center_id,
            "total_batches": total_batches,
            "batches_by_status": status_counts,
            "total_planned": total_planned,
            "total_actual": total_actual,
            "completion_percent": completion_percent,
        }
