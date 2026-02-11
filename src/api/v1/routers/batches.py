from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_async_session
from ....core.exceptions import AppException
from ....data.models.batch import BatchStatus
from ....domain.exceptions import (
    BatchAlreadyExistsError,
    BatchNotFoundError,
    InvalidBatchStatusError,
)
from ....domain.services.batch_service import BatchService
from ..schemas.batch import BatchCreate, BatchRead, BatchUpdate
from ..schemas.common import PaginatedResponse

router = APIRouter(prefix="/batches", tags=["Batches"])


@router.post(
    "/",
    response_model=BatchRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новую партию",
    responses={
        201: {"description": "Партия успешно создана"},
        400: {"description": "Партия с таким номером уже существует"},
    },
)
async def create_batch(
    data: BatchCreate,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BatchRead:
    """
    Создать новую партию (сменное задание).

    **Обязательные поля:**
    - `number`: уникальный номер партии (например, B-2026-001)
    - `work_center_id`: ID рабочего центра
    - `shift_date`: дата смены
    - `shift_number`: номер смены (1, 2 или 3)
    - `planned_quantity`: плановое количество продукции

    **Валидация:**
    - Номер партии должен быть уникальным
    - Номер смены: 1, 2 или 3
    - Плановое количество > 0

    **Возвращает:** созданную партию со статусом `planned`.
    """
    service = BatchService(session)

    try:
        batch = await service.create(
            number=data.number,
            work_center_id=data.work_center_id,
            shift_date=data.shift_date,
            shift_number=data.shift_number,
            planned_quantity=data.planned_quantity,
        )
    except BatchAlreadyExistsError as e:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Партия с таким номером уже существует",
            details=e.details,
        ) from e

    return BatchRead.model_validate(batch)


@router.get(
    "/",
    response_model=PaginatedResponse[BatchRead],
    summary="Получить список партий",
    responses={
        200: {"description": "Список партий с пагинацией"},
    },
)
async def get_batches(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    status_filter: Annotated[BatchStatus | None, Query(alias="status")] = None,
    work_center_id: Annotated[int | None, Query(gt=0)] = None,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
) -> PaginatedResponse[BatchRead]:
    """
    Получить список партий с фильтрацией и пагинацией.

    **Query-параметры:**
    - `offset`: смещение (по умолчанию 0)
    - `limit`: количество записей (от 1 до 500, по умолчанию 100)
    - `status`: фильтр по статусу (planned, in_progress, completed, cancelled)
    - `work_center_id`: фильтр по рабочему центру
    - `date_from`: начало диапазона дат (ISO формат)
    - `date_to`: конец диапазона дат (ISO формат)

    **Возвращает:** объект с полями:
    - `items`: массив партий
    - `total`: общее количество записей
    - `offset`: текущее смещение
    - `limit`: размер страницы
    """
    from datetime import datetime

    service = BatchService(session)

    # Парсинг дат из строк
    date_from_parsed = datetime.fromisoformat(date_from) if date_from else None
    date_to_parsed = datetime.fromisoformat(date_to) if date_to else None

    items, total = await service.get_list(
        offset=offset,
        limit=limit,
        status=status_filter,
        work_center_id=work_center_id,
        date_from=date_from_parsed,
        date_to=date_to_parsed,
    )

    return PaginatedResponse(
        items=[BatchRead.model_validate(item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{batch_id}",
    response_model=BatchRead,
    summary="Получить партию по ID",
    responses={
        200: {"description": "Партия найдена"},
        404: {"description": "Партия не найдена"},
    },
)
async def get_batch(
    batch_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BatchRead:
    """
    Получить одну партию по ID.

    **Path-параметры:**
    - `batch_id`: ID партии

    **Возвращает:** партию со всеми полями.
    """
    service = BatchService(session)

    try:
        batch = await service.get_by_id(batch_id)
    except BatchNotFoundError as e:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Партия не найдена",
            details=e.details,
        ) from e

    return BatchRead.model_validate(batch)


@router.patch(
    "/{batch_id}",
    response_model=BatchRead,
    summary="Обновить партию",
    responses={
        200: {"description": "Партия обновлена"},
        404: {"description": "Партия не найдена"},
        400: {"description": "Недопустимый переход статуса"},
    },
)
async def update_batch(
    batch_id: int,
    data: BatchUpdate,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BatchRead:
    """
    Обновить данные партии.

    **Path-параметры:**
    - `batch_id`: ID партии

    **Поля для обновления (все опциональны):**
    - `shift_date`: дата смены
    - `shift_number`: номер смены (1, 2 или 3)
    - `planned_quantity`: плановое количество
    - `actual_quantity`: фактическое количество
    - `status`: новый статус

    **Логика:**
    - Если передан `status` - выполняется смена статуса с валидацией переходов
    - Остальные поля обновляются напрямую

    **Валидация статусов:**
    - `planned` → `in_progress`, `cancelled`
    - `in_progress` → `completed`, `cancelled`
    - `completed` → (нельзя изменить)
    - `cancelled` → (нельзя изменить)

    **Возвращает:** обновленную партию.
    """
    service = BatchService(session)

    try:
        # Если передан статус - делаем change_status
        if data.status is not None:
            batch = await service.change_status(batch_id, data.status)
        else:
            # Иначе - обычное обновление
            batch = await service.update(
                batch_id,
                shift_date=data.shift_date,
                shift_number=data.shift_number,
                planned_quantity=data.planned_quantity,
                actual_quantity=data.actual_quantity,
            )
    except BatchNotFoundError as e:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Партия не найдена",
            details=e.details,
        ) from e
    except InvalidBatchStatusError as e:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Недопустимый переход статуса",
            details=e.details,
        ) from e

    return BatchRead.model_validate(batch)


@router.delete(
    "/{batch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить партию",
    responses={
        204: {"description": "Партия успешно удалена"},
        404: {"description": "Партия не найдена"},
    },
)
async def delete_batch(
    batch_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """
    Удалить партию по ID.

    **Path-параметры:**
    - `batch_id`: ID партии

    **Возвращает:** HTTP 204 (пустой ответ) при успехе.

    **Примечание:** Физическое удаление из БД. Для "мягкого" удаления
    используйте смену статуса на `cancelled`.
    """
    service = BatchService(session)

    try:
        await service.delete(batch_id)
    except BatchNotFoundError as e:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Партия не найдена",
            details=e.details,
        ) from e
