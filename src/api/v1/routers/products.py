from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_async_session
from ....core.exceptions import AppException
from ....data.models.product import ProductStatus
from ....domain.exceptions import (
    InvalidProductStatusError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
)
from ....domain.services.product_service import ProductService
from ..schemas.common import PaginatedResponse, SuccessResponse
from ..schemas.product import (
    ProductBulkStatusUpdate,
    ProductCreate,
    ProductRead,
    ProductUpdate,
)

router = APIRouter(prefix="/products", tags=["Products"])


@router.post(
    "/",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать единицу продукции",
    responses={
        201: {"description": "Продукция успешно создана"},
        400: {"description": "Продукция с таким кодом уже существует"},
    },
)
async def create_product(
    data: ProductCreate,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ProductRead:
    """
    Создать новую единицу продукции.

    **Обязательные поля:**
    - `code`: уникальный код продукции (серийный номер, код маркировки)
    - `batch_id`: ID партии, в рамках которой произведена
    - `product_type`: тип продукции (bottle, box, pallet)

    **Опциональные поля:**
    - `extra_data`: дополнительные данные (JSON-строка)
    - `produced_at`: время производства (по умолчанию — текущее)

    **Возвращает:** созданную единицу продукции со статусом `produced`.
    """
    service = ProductService(session)

    try:
        product = await service.create(
            code=data.code,
            batch_id=data.batch_id,
            product_type=data.product_type,
            extra_data=data.extra_data,
            produced_at=data.produced_at,
        )
    except ProductAlreadyExistsError as e:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Продукция с таким кодом уже существует",
            details=e.details,
        ) from e

    return ProductRead.model_validate(product)


@router.get(
    "/",
    response_model=PaginatedResponse[ProductRead],
    summary="Получить список продукции",
    responses={
        200: {"description": "Список продукции с пагинацией"},
    },
)
async def get_products(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    batch_id: Annotated[int | None, Query(gt=0)] = None,
    status_filter: Annotated[ProductStatus | None, Query(alias="status")] = None,
    product_type: Annotated[str | None, Query()] = None,
) -> PaginatedResponse[ProductRead]:
    """
    Получить список продукции с фильтрацией и пагинацией.

    **Query-параметры:**
    - `offset`: смещение (по умолчанию 0)
    - `limit`: количество записей (от 1 до 500, по умолчанию 100)
    - `batch_id`: фильтр по партии
    - `status`: фильтр по статусу (produced, aggregated, rejected, shipped)
    - `product_type`: фильтр по типу продукции

    **Возвращает:** объект с полями:
    - `items`: массив продукции
    - `total`: общее количество записей
    - `offset`: текущее смещение
    - `limit`: размер страницы
    """
    service = ProductService(session)

    items, total = await service.get_list(
        offset=offset,
        limit=limit,
        batch_id=batch_id,
        status=status_filter,
        product_type=product_type,
    )

    return PaginatedResponse(
        items=[ProductRead.model_validate(item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{product_id}",
    response_model=ProductRead,
    summary="Получить продукцию по ID",
    responses={
        200: {"description": "Продукция найдена"},
        404: {"description": "Продукция не найдена"},
    },
)
async def get_product(
    product_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ProductRead:
    """
    Получить единицу продукции по ID.

    **Path-параметры:**
    - `product_id`: ID единицы продукции

    **Возвращает:** продукцию со всеми полями.
    """
    service = ProductService(session)

    try:
        product = await service.get_by_id(product_id)
    except ProductNotFoundError as e:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Продукция не найдена",
            details=e.details,
        ) from e

    return ProductRead.model_validate(product)


@router.patch(
    "/{product_id}",
    response_model=ProductRead,
    summary="Обновить продукцию",
    responses={
        200: {"description": "Продукция обновлена"},
        404: {"description": "Продукция не найдена"},
        400: {"description": "Недопустимый переход статуса"},
    },
)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ProductRead:
    """
    Обновить данные единицы продукции.

    **Path-параметры:**
    - `product_id`: ID единицы продукции

    **Поля для обновления (все опциональны):**
    - `status`: новый статус
    - `product_type`: тип продукции
    - `extra_data`: дополнительные данные

    **Логика:**
    - Если передан `status` — выполняется смена статуса с валидацией переходов
    - Остальные поля обновляются напрямую

    **Валидация статусов:**
    - `produced` → `aggregated`, `rejected`
    - `aggregated` → `shipped`
    - `rejected` → (нельзя изменить)
    - `shipped` → (нельзя изменить)

    **Возвращает:** обновлённую продукцию.
    """
    service = ProductService(session)

    try:
        if data.status is not None:
            product = await service.change_status(product_id, data.status)
        else:
            product = await service.update(
                product_id,
                product_type=data.product_type,
                extra_data=data.extra_data,
            )
    except ProductNotFoundError as e:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Продукция не найдена",
            details=e.details,
        ) from e
    except InvalidProductStatusError as e:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Недопустимый переход статуса",
            details=e.details,
        ) from e

    return ProductRead.model_validate(product)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить продукцию",
    responses={
        204: {"description": "Продукция успешно удалена"},
        404: {"description": "Продукция не найдена"},
    },
)
async def delete_product(
    product_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """
    Удалить единицу продукции по ID.

    **Path-параметры:**
    - `product_id`: ID единицы продукции

    **Возвращает:** HTTP 204 (пустой ответ) при успехе.
    """
    service = ProductService(session)

    try:
        await service.delete(product_id)
    except ProductNotFoundError as e:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Продукция не найдена",
            details=e.details,
        ) from e


@router.post(
    "/bulk-status",
    response_model=SuccessResponse,
    summary="Массово обновить статус продукции",
    responses={
        200: {"description": "Статусы успешно обновлены"},
        404: {"description": "Продукция не найдена"},
        400: {"description": "Недопустимый переход статуса"},
    },
)
async def bulk_update_status(
    data: ProductBulkStatusUpdate,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> SuccessResponse:
    """
    Массово обновить статус продукции по списку кодов.

    **Тело запроса:**
    - `codes`: список кодов продукции (от 1 до 1000)
    - `new_status`: новый статус

    **Логика:**
    - Проверяет, что коды существуют в БД
    - Валидирует переход статуса для каждой найденной единицы
    - Обновляет статус одним SQL-запросом

    **Возвращает:** сообщение с количеством обновлённых записей.
    """
    service = ProductService(session)

    try:
        updated = await service.bulk_update_status(data.codes, data.new_status)
    except ProductNotFoundError as e:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Продукция не найдена",
            details=e.details,
        ) from e
    except InvalidProductStatusError as e:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Недопустимый переход статуса",
            details=e.details,
        ) from e

    return SuccessResponse(message=f"Обновлено записей: {updated}")
