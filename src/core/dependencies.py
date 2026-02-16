from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_async_session

# === Типизированные зависимости (type aliases) ===

# Сессия БД — вместо Annotated[AsyncSession, Depends(get_async_session)] в каждом роутере
DbSession = Annotated[AsyncSession, Depends(get_async_session)]

# Настройки приложения
AppSettings = Annotated[Settings, Depends(get_settings)]


# === Общие Query-параметры ===


class PaginationParams:
    """
    Параметры пагинации для list-эндпоинтов.

    Использование в роутерах:
        @router.get("/items")
        async def get_items(pagination: PaginationDep):
            items = await service.get_list(
                offset=pagination.offset,
                limit=pagination.limit,
            )
    """

    def __init__(
        self,
        offset: Annotated[int, Query(ge=0, description="Смещение")] = 0,
        limit: Annotated[
            int,
            Query(ge=1, le=500, description="Количество записей"),
        ] = 100,
    ) -> None:
        self.offset = offset
        self.limit = limit


PaginationDep = Annotated[PaginationParams, Depends()]
