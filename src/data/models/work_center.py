from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ...core.database import Base


class WorkCenter(Base):
    """
    Модель рабочего центра (производственного участка).
    Рабочий центр - это место выполнения сменных заданий:
    линия розлива, участок упаковки, цех сборки и т.д.
    """

    __tablename__ = 'work_centers'

    # Первичный ключ
    id: Mapped[int] = mapped_column(primary_key=True)

    # Уникальный код участка (например: "LINE-01", "PACK-A")
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)

    # Название участка (например: "Линия розлива №1")
    name: Mapped[str] = mapped_column(String(255))

    # Активен ли участок (можно отключить без удаления)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Связь с партиями (сменными заданиями)
    # Один рабочий центр -> много партий
    if TYPE_CHECKING:
        from .batch import Batch

    batches: Mapped[list["Batch"]] = relationship(
        "Batch",
        back_populates="work_center",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<WorkCenter(id={self.id}, code='{self.code}', name='{self.name}')>"