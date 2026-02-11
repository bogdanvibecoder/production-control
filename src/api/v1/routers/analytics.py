from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_async_session
from ....core.exceptions import AppException
from ....domain.exceptions import BatchNotFoundError
from ....domain.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get(
    "/batches/summary",
    summary="Сводка по партиям",
    responses={
        200: {"description": "Общая статистика по партиям"},
    },
)
async def get_batch_summary(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, Any]:
    """
    Общая сводка: количество партий по статусам.

    **Возвращает:**
    - `total`: общее количество партий
    - `by_status`: количество по каждому статусу
    """
    service = AnalyticsService(session)
    return await service.get_batch_summary()


@router.get(
    "/batches/{batch_id}",
    summary="Аналитика по партии",
    responses={
        200: {"description": "Детальная аналитика партии"},
        404: {"description": "Партия не найдена"},
    },
)
async def get_batch_details(
    batch_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, Any]:
    """
    Детальная аналитика по конкретной партии:
    план/факт, процент выполнения, продукция по статусам.
    """
    service = AnalyticsService(session)

    try:
        return await service.get_batch_details(batch_id)
    except BatchNotFoundError as e:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Партия не найдена",
            details=e.details,
        ) from e


@router.get(
    "/production-report",
    summary="Отчёт по производству за период",
    responses={
        200: {"description": "Производственный отчёт"},
    },
)
async def get_production_report(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    date_from: Annotated[datetime, Query()],
    date_to: Annotated[datetime, Query()],
    work_center_id: Annotated[int | None, Query(gt=0)] = None,
) -> dict[str, Any]:
    """
    Отчёт по производству за период: партии, план/факт, процент выполнения.

    **Обязательные параметры:**
    - `date_from`: начало периода (ISO формат)
    - `date_to`: конец периода (ISO формат)

    **Опционально:**
    - `work_center_id`: фильтр по рабочему центру
    """
    service = AnalyticsService(session)

    return await service.get_production_report(
        date_from=date_from,
        date_to=date_to,
        work_center_id=work_center_id,
    )
