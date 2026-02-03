from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Базовый репозиторий с CRUD-операциями.
    Все репозитории наследуются от этого класса.
    """

    def __init__(self, session: AsyncSession, model: type[ModelType]) -> None:
        """
        Args:
            session: Асинхронная сессия SQLAlchemy
            model: Класс модели (например, Batch, Product)
        """
        self._session = session
        self._model = model

    async def get_by_id(self, id: int) -> ModelType | None:
        """Получить запись по ID."""
        return await self._session.get(self._model, id)

    async def get_all(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[ModelType]:
        """Получить список записей с пагинацией."""
        stmt = select(self._model).offset(offset).limit(limit)
        result = await self._session.scalars(stmt)
        return result.all()

    async def count(self) -> int:
        """Получить общее количество записей."""
        stmt = select(func.count()).select_from(self._model)
        result = await self._session.scalar(stmt)
        return result or 0

    async def create(self, **kwargs: Any) -> ModelType:
        """Создать новую запись."""
        instance = self._model(**kwargs)
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def update(
        self,
        id: int,
        **kwargs: Any,
    ) -> ModelType | None:
        """Обновить запись по ID."""
        instance = await self.get_by_id(id)
        if instance is None:
            return None
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def delete(self, id: int) -> bool:
        """Удалить запись по ID. Возвращает True если удалено."""
        instance = await self.get_by_id(id)
        if instance is None:
            return False
        await self._session.delete(instance)
        await self._session.flush()
        return True
