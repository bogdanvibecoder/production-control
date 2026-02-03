from collections.abc import Sequence

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.product import Product, ProductStatus
from .base_repository import BaseRepository


class ProductRepository(BaseRepository[Product]):
    """
    Репозиторий для работы с единицами продукции.
    Наследует базовые CRUD-операции и добавляет специфичные методы.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Product)

    async def get_by_code(self, code: str) -> Product | None:
        """Получить продукцию по коду."""
        stmt = select(Product).where(Product.code == code)
        result = await self._session.scalar(stmt)
        return result

    async def get_by_codes(self, codes: list[str]) -> Sequence[Product]:
        """Получить продукцию по списку кодов."""
        stmt = select(Product).where(Product.code.in_(codes))
        result = await self._session.scalars(stmt)
        return result.all()

    async def get_by_batch(
        self,
        batch_id: int,
        *,
        status: ProductStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Product]:
        """
        Получить продукцию по партии.
        Args:
            batch_id: ID партии
            status: Опционально - фильтр по статусу
        """
        conditions = [Product.batch_id == batch_id]
        if status is not None:
            conditions.append(Product.status == status)

        stmt = (
            select(Product)
            .where(and_(*conditions))
            .order_by(Product.produced_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return result.all()

    async def get_by_status(
        self,
        status: ProductStatus,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Product]:
        """Получить продукцию по статусу."""
        stmt = (
            select(Product)
            .where(Product.status == status)
            .order_by(Product.produced_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return result.all()

    async def count_by_batch(
        self,
        batch_id: int,
        *,
        status: ProductStatus | None = None,
    ) -> int:
        """
        Подсчитать количество продукции в партии.
        Args:
            batch_id: ID партии
            status: Опционально - считать только с определённым статусом
        """

        conditions = [Product.batch_id == batch_id]
        if status is not None:
            conditions.append(Product.status == status)

        stmt = select(func.count()).select_from(Product).where(and_(*conditions))
        result = await self._session.scalar(stmt)
        return result or 0

    async def update_status_bulk(
        self,
        codes: list[str],
        new_status: ProductStatus,
    ) -> int:
        """
        Массово обновить статус продукции по списку кодов.
        Возвращает количество обновлённых записей.
        Args:
            codes: Список кодов продукции
            new_status: Новый статус
        """
        stmt = update(Product).where(Product.code.in_(codes)).values(status=new_status)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount  # type: ignore[no-any-return, attr-defined]
