"""Unit-тесты для ProductService."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models.batch import Batch
from src.data.models.product import Product, ProductStatus
from src.domain.exceptions import (
    InvalidProductStatusError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
)
from src.domain.services.product_service import ProductService

# ============================================================================
# Создание продукции
# ============================================================================


class TestCreateProduct:
    """Тесты создания единицы продукции."""

    async def test_create_success(self, session: AsyncSession, batch: Batch) -> None:
        """Продукция успешно создаётся с корректными данными."""
        service = ProductService(session)

        product = await service.create(
            code="NEW-PRD-001",
            batch_id=batch.id,
            product_type="bottle",
            extra_data='{"weight": 0.5}',
        )

        assert product.id is not None
        assert product.code == "NEW-PRD-001"
        assert product.batch_id == batch.id
        assert product.product_type == "bottle"
        assert product.extra_data == '{"weight": 0.5}'
        assert product.status == ProductStatus.PRODUCED

    async def test_create_with_produced_at(self, session: AsyncSession, batch: Batch) -> None:
        """Продукция создаётся с указанным временем производства."""
        service = ProductService(session)
        ts = datetime(2026, 2, 15, 10, 30, tzinfo=UTC)

        product = await service.create(
            code="NEW-PRD-002",
            batch_id=batch.id,
            product_type="box",
            produced_at=ts,
        )

        # SQLite не хранит timezone, сравниваем по дате и времени
        assert product.produced_at.year == 2026
        assert product.produced_at.month == 2
        assert product.produced_at.day == 15
        assert product.produced_at.hour == 10
        assert product.produced_at.minute == 30

    async def test_create_duplicate_code_raises(
        self, session: AsyncSession, product: Product
    ) -> None:
        """Создание продукции с существующим кодом вызывает ошибку."""
        service = ProductService(session)

        with pytest.raises(ProductAlreadyExistsError):
            await service.create(
                code=product.code,  # "PRD-001" — уже существует
                batch_id=product.batch_id,
                product_type="bottle",
            )


# ============================================================================
# Получение продукции
# ============================================================================


class TestGetProduct:
    """Тесты получения продукции."""

    async def test_get_by_id_success(self, session: AsyncSession, product: Product) -> None:
        """Продукция находится по существующему ID."""
        service = ProductService(session)

        result = await service.get_by_id(product.id)

        assert result.id == product.id
        assert result.code == product.code

    async def test_get_by_id_not_found(self, session: AsyncSession) -> None:
        """Несуществующий ID вызывает ProductNotFoundError."""
        service = ProductService(session)

        with pytest.raises(ProductNotFoundError):
            await service.get_by_id(99999)

    async def test_get_by_code_success(self, session: AsyncSession, product: Product) -> None:
        """Продукция находится по уникальному коду."""
        service = ProductService(session)

        result = await service.get_by_code(product.code)

        assert result.code == product.code

    async def test_get_by_code_not_found(self, session: AsyncSession) -> None:
        """Несуществующий код вызывает ProductNotFoundError."""
        service = ProductService(session)

        with pytest.raises(ProductNotFoundError):
            await service.get_by_code("NONEXISTENT-CODE")

    async def test_get_list_no_filters(self, session: AsyncSession, product: Product) -> None:
        """Список продукции возвращается без фильтров."""
        service = ProductService(session)

        items, total = await service.get_list()

        assert total >= 1
        assert len(items) >= 1

    async def test_get_list_filter_by_batch(
        self, session: AsyncSession, product: Product, batch: Batch
    ) -> None:
        """Фильтрация по batch_id возвращает только нужную продукцию."""
        service = ProductService(session)

        items, total = await service.get_list(batch_id=batch.id)

        assert total >= 1
        assert all(item.batch_id == batch.id for item in items)

    async def test_get_list_filter_by_status(self, session: AsyncSession, product: Product) -> None:
        """Фильтрация по статусу работает корректно."""
        service = ProductService(session)

        items, _ = await service.get_list(status=ProductStatus.PRODUCED)

        assert all(item.status == ProductStatus.PRODUCED for item in items)


# ============================================================================
# Обновление продукции
# ============================================================================


class TestUpdateProduct:
    """Тесты обновления продукции."""

    async def test_update_product_type(self, session: AsyncSession, product: Product) -> None:
        """Обновление типа продукции работает."""
        service = ProductService(session)

        updated = await service.update(product.id, product_type="pallet")

        assert updated.product_type == "pallet"

    async def test_update_extra_data(self, session: AsyncSession, product: Product) -> None:
        """Обновление дополнительных данных работает."""
        service = ProductService(session)

        updated = await service.update(product.id, extra_data='{"line": 3}')

        assert updated.extra_data == '{"line": 3}'

    async def test_update_no_data_returns_same(
        self, session: AsyncSession, product: Product
    ) -> None:
        """Обновление без данных возвращает продукцию без изменений."""
        service = ProductService(session)

        result = await service.update(product.id)

        assert result.id == product.id

    async def test_update_not_found_raises(self, session: AsyncSession) -> None:
        """Обновление несуществующей продукции вызывает ошибку."""
        service = ProductService(session)

        with pytest.raises(ProductNotFoundError):
            await service.update(99999, product_type="box")


# ============================================================================
# Удаление продукции
# ============================================================================


class TestDeleteProduct:
    """Тесты удаления продукции."""

    async def test_delete_success(self, session: AsyncSession, product: Product) -> None:
        """Существующая продукция успешно удаляется."""
        service = ProductService(session)

        await service.delete(product.id)

        with pytest.raises(ProductNotFoundError):
            await service.get_by_id(product.id)

    async def test_delete_not_found_raises(self, session: AsyncSession) -> None:
        """Удаление несуществующей продукции вызывает ошибку."""
        service = ProductService(session)

        with pytest.raises(ProductNotFoundError):
            await service.delete(99999)


# ============================================================================
# Переходы статусов
# ============================================================================


class TestProductStatusTransitions:
    """Тесты переходов статусов продукции — ключевая бизнес-логика."""

    # --- Допустимые переходы ---

    async def test_produced_to_aggregated(self, session: AsyncSession, product: Product) -> None:
        """produced → aggregated: допустимый переход."""
        service = ProductService(session)

        result = await service.change_status(product.id, ProductStatus.AGGREGATED)

        assert result.status == ProductStatus.AGGREGATED

    async def test_produced_to_rejected(self, session: AsyncSession, product: Product) -> None:
        """produced → rejected: допустимый переход."""
        service = ProductService(session)

        result = await service.change_status(product.id, ProductStatus.REJECTED)

        assert result.status == ProductStatus.REJECTED

    async def test_aggregated_to_shipped(
        self, session: AsyncSession, product_aggregated: Product
    ) -> None:
        """aggregated → shipped: допустимый переход."""
        service = ProductService(session)

        result = await service.change_status(product_aggregated.id, ProductStatus.SHIPPED)

        assert result.status == ProductStatus.SHIPPED

    # --- Недопустимые переходы ---

    async def test_produced_to_shipped_raises(
        self, session: AsyncSession, product: Product
    ) -> None:
        """produced → shipped: запрещено (нужен aggregated)."""
        service = ProductService(session)

        with pytest.raises(InvalidProductStatusError):
            await service.change_status(product.id, ProductStatus.SHIPPED)

    async def test_rejected_to_any_raises(self, session: AsyncSession, product: Product) -> None:
        """rejected → любой: запрещено (терминальный статус)."""
        service = ProductService(session)

        await service.change_status(product.id, ProductStatus.REJECTED)

        with pytest.raises(InvalidProductStatusError):
            await service.change_status(product.id, ProductStatus.PRODUCED)

    async def test_shipped_to_any_raises(
        self, session: AsyncSession, product_aggregated: Product
    ) -> None:
        """shipped → любой: запрещено (терминальный статус)."""
        service = ProductService(session)

        await service.change_status(product_aggregated.id, ProductStatus.SHIPPED)

        with pytest.raises(InvalidProductStatusError):
            await service.change_status(product_aggregated.id, ProductStatus.AGGREGATED)

    async def test_change_status_not_found_raises(self, session: AsyncSession) -> None:
        """Смена статуса несуществующей продукции вызывает ошибку."""
        service = ProductService(session)

        with pytest.raises(ProductNotFoundError):
            await service.change_status(99999, ProductStatus.AGGREGATED)


# ============================================================================
# Массовое обновление статуса
# ============================================================================


class TestBulkUpdateStatus:
    """Тесты массового обновления статуса по списку кодов."""

    async def test_bulk_update_success(self, session: AsyncSession, batch: Batch) -> None:
        """Массовое обновление статуса работает для нескольких единиц."""
        service = ProductService(session)

        # Создаём 3 единицы в статусе PRODUCED
        codes = []
        for i in range(3):
            p = await service.create(
                code=f"BULK-{i:03d}",
                batch_id=batch.id,
                product_type="bottle",
            )
            codes.append(p.code)

        # Массово переводим в AGGREGATED
        updated = await service.bulk_update_status(codes, ProductStatus.AGGREGATED)

        assert updated == 3

    async def test_bulk_update_no_products_raises(self, session: AsyncSession) -> None:
        """Массовое обновление с несуществующими кодами вызывает ошибку."""
        service = ProductService(session)

        with pytest.raises(ProductNotFoundError):
            await service.bulk_update_status(
                ["FAKE-001", "FAKE-002"],
                ProductStatus.AGGREGATED,
            )

    async def test_bulk_update_invalid_transition_raises(
        self, session: AsyncSession, product: Product
    ) -> None:
        """Массовое обновление с недопустимым переходом вызывает ошибку."""
        service = ProductService(session)

        with pytest.raises(InvalidProductStatusError):
            await service.bulk_update_status(
                [product.code],
                ProductStatus.SHIPPED,  # produced → shipped запрещено
            )
