from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, ForeignKey, DateTime, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.database import Base


if TYPE_CHECKING:
    from .work_center import WorkCenter
    from .product import Product


class BatchStatus(str, Enum):
    """Статусы жизненного цикла партии"""
    PLANNED = "planned"  # Запланирована
    IN_PROGRESS = "in_progress"  # В работе
    COMPLETED = "completed"  # Завершена
    CANCELLED = "cancelled"  # Отменена


class Batch(Base):
    """
    Модель партии (сменного задания).
    Партия - это задание на производство определённого количества
    продукции на конкретном рабочем центре в определённую смену.
    """

    __tablename__ = "batches"

    # Первичный ключ
    id: Mapped[int] = mapped_column(primary_key=True)

    # Номер партии (уникальный идентификатор для производства)
    number: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    # Внешний ключ на рабочий центр
    work_center_id: Mapped[int] = mapped_column(
        ForeignKey("work_centers.id", ondelete="RESTRICT"),
        index=True,
    )

    # Дата смены и номер смены (1, 2, 3)
    shift_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    shift_number: Mapped[int] = mapped_column(Integer)

    # Статус партии
    status: Mapped[BatchStatus] = mapped_column(
        String(20),
        default=BatchStatus.PLANNED,
    )

    # Плановое количество продукции
    planned_quantity: Mapped[Decimal] = mapped_column(
        Numeric(15, 3),
        default=Decimal("0"),
    )

    # Фактическое количество (заполняется по мере производства)
    actual_quantity: Mapped[Decimal] = mapped_column(
        Numeric(15, 3),
        default=Decimal("0"),
    )

    # Время начала и завершения работы
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    # Связь с рабочим центром (Many-to-One)
    work_center: Mapped["WorkCenter"] = relationship(
        "WorkCenter",
        back_populates="batches",
        lazy="joined",
    )

    # Связь с продукцией (One-to-Many)
    products: Mapped[list["Product"]] = relationship(
        "Product",
        back_populates="batch",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Batch(id={self.id}, number='{self.number}', status={self.status.value})>"
