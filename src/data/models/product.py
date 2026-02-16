from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.database import Base

if TYPE_CHECKING:
    from .batch import Batch


class ProductStatus(str, Enum):
    """Статусы единицы продукции"""
    PRODUCED = "produced"  # Произведена
    REJECTED = "rejected"  # Отбракована
    AGGREGATED = "aggregated"  # Агрегирована (упакована в короб/паллету)
    SHIPPED = "shipped"  # Отгружена


class Product(Base):
    """
    Модель единицы продукции.
    Представляет конкретный экземпляр продукции с уникальным кодом,
    произведённый в рамках определённой партии (сменного задания).
    """

    __tablename__ = "products"

    # Первичный ключ
    id: Mapped[int] = mapped_column(primary_key=True)

    # Уникальный код продукции (серийный номер, код маркировки)
    code: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # Внешний ключ на партию
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"),
        index=True,
    )

    # Статус продукции
    status: Mapped[ProductStatus] = mapped_column(
        String(20),
        default=ProductStatus.PRODUCED,
    )

    # Тип продукции (например: "bottle", "box", "pallet")
    product_type: Mapped[str] = mapped_column(String(50))

    # Дополнительные данные (JSON-подобное текстовое поле)
    # Например: вес, объём, номер линии, оператор
    extra_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Время производства (сканирования)
    produced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Служебные временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Связь с партией (Many-to-One)
    batch: Mapped["Batch"] = relationship(
        "Batch",
        back_populates="products",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, code='{self.code}', status={self.status.value})>"
