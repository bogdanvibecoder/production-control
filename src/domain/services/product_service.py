from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...data.models.product import Product, ProductStatus
from ...data.repositories.product_repository import ProductRepository
from ..exceptions import (
    InvalidProductStatusError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
)

ALLOWED_PRODUCT_TRANSITIONS: dict[ProductStatus, set[ProductStatus]] = {
    ProductStatus.PRODUCED: {ProductStatus.AGGREGATED, ProductStatus.REJECTED},
    ProductStatus.AGGREGATED: {ProductStatus.SHIPPED},
    ProductStatus.REJECTED: set(),
    ProductStatus.SHIPPED: set(),
}


class ProductService:
    """Сервис бизнес-логики для работы с продукцией."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ProductRepository(session)

    async def get_by_id(self, product_id: int) -> Product:
        """Получить продукцию по ID."""
        product = await self._repo.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(details={"product_id": product_id})
        return product

    async def get_by_code(self, code: str) -> Product:
        """Получить продукцию по уникальному коду."""
        product = await self._repo.get_by_code(code)
        if product is None:
            raise ProductNotFoundError(details={"code": code})
        return product

    async def get_list(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        batch_id: int | None = None,
        status: ProductStatus | None = None,
        product_type: str | None = None,
    ) -> tuple[Sequence[Product], int]:
        """Получить список продукции с фильтрацией и пагинацией."""
        if batch_id is not None:
            items = await self._repo.get_by_batch(
                batch_id,
                status=status,
                offset=offset,
                limit=limit,
            )
            total = await self._repo.count_by_batch(batch_id, status=status)
        elif status is not None:
            items = await self._repo.get_by_status(
                status,
                offset=offset,
                limit=limit,
            )
            total = await self._repo.count()
        else:
            items = await self._repo.get_all(offset=offset, limit=limit)
            total = await self._repo.count()

        return items, total

    async def create(
        self,
        *,
        code: str,
        batch_id: int,
        product_type: str,
        extra_data: str | None = None,
        produced_at: datetime | None = None,
    ) -> Product:
        """Создать единицу продукции."""
        existing = await self._repo.get_by_code(code)
        if existing is not None:
            raise ProductAlreadyExistsError(details={"code": code})

        kwargs: dict[str, Any] = {
            "code": code,
            "batch_id": batch_id,
            "product_type": product_type,
        }
        if extra_data is not None:
            kwargs["extra_data"] = extra_data
        if produced_at is not None:
            kwargs["produced_at"] = produced_at

        product = await self._repo.create(**kwargs)
        await self._session.commit()
        return product

    async def update(
        self,
        product_id: int,
        *,
        product_type: str | None = None,
        extra_data: str | None = None,
    ) -> Product:
        """Обновить данные продукции (без смены статуса)."""
        data: dict[str, Any] = {}
        if product_type is not None:
            data["product_type"] = product_type
        if extra_data is not None:
            data["extra_data"] = extra_data

        if not data:
            return await self.get_by_id(product_id)

        product = await self._repo.update(product_id, **data)
        if product is None:
            raise ProductNotFoundError(details={"product_id": product_id})
        await self._session.commit()
        return product

    async def delete(self, product_id: int) -> None:
        """Удалить единицу продукции."""
        deleted = await self._repo.delete(product_id)
        if not deleted:
            raise ProductNotFoundError(details={"product_id": product_id})
        await self._session.commit()

    async def change_status(
        self,
        product_id: int,
        new_status: ProductStatus,
    ) -> Product:
        """Сменить статус продукции с валидацией перехода."""
        product = await self.get_by_id(product_id)

        self._validate_transition(product.status, new_status)

        updated = await self._repo.update(product_id, status=new_status)
        if updated is None:
            raise ProductNotFoundError(details={"product_id": product_id})
        await self._session.commit()
        return updated

    async def bulk_update_status(
        self,
        codes: list[str],
        new_status: ProductStatus,
    ) -> int:
        """
        Массово обновить статус продукции по списку кодов.
        Возвращает количество обновлённых записей.
        """
        products = await self._repo.get_by_codes(codes)

        if not products:
            raise ProductNotFoundError(
                message="Ни одна единица продукции не найдена",
                details={"codes": codes},
            )

        for product in products:
            self._validate_transition(product.status, new_status)

        updated = await self._repo.update_status_bulk(codes, new_status)
        await self._session.commit()
        return updated

    @staticmethod
    def _validate_transition(
        current: ProductStatus,
        new: ProductStatus,
    ) -> None:
        """Проверить допустимость перехода статуса."""
        allowed = ALLOWED_PRODUCT_TRANSITIONS.get(current, set())
        if new not in allowed:
            raise InvalidProductStatusError(
                details={
                    "current_status": current.value,
                    "new_status": new.value,
                    "allowed_transitions": [s.value for s in allowed],
                },
            )
