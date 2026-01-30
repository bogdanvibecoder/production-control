from datetime import datetime
from enum import Enum

from sqlalchemy import String, Integer, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.database import Base


class WebhookEvent(str, Enum):
    """События, на которые можно подписаться"""
    BATCH_CREATED = "batch.created"
    BATCH_STARTED = "batch.started"
    BATCH_COMPLETED = "batch.completed"
    BATCH_CANCELLED = "batch.cancelled"
    PRODUCT_AGGREGATED = "product.aggregated"


class DeliveryStatus(str, Enum):
    """Статус попытки доставки webhook"""
    PENDING = "pending"  # Ожидает отправки
    SUCCESS = "success"  # Успешно доставлен (HTTP 2xx)
    FAILED = "failed"  # Ошибка (HTTP 4xx/5xx или timeout)
    RETRYING = "retrying"  # Повторная попытка запланирована


class WebhookSubscription(Base):
    """
    Подписка на webhook-уведомления.
    Определяет endpoint, на который отправляются уведомления
    о выбранных событиях в системе.
    """

    __tablename__ = "webhook_subscriptions"

    # Первичный ключ
    id: Mapped[int] = mapped_column(primary_key=True)

    # Название подписки (для удобства в UI)
    name: Mapped[str] = mapped_column(String(255))

    # URL, куда отправлять POST-запросы
    target_url: Mapped[str] = mapped_column(String(2048))

    # Тип события (batch.created, batch.completed и т.д.)
    event_type: Mapped[WebhookEvent] = mapped_column(String(50), index=True)

    # Секретный ключ для HMAC-подписи (чтобы получатель мог проверить подлинность)
    secret: Mapped[str] = mapped_column(String(255))

    # Активна ли подписка (можно временно отключить)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

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

    # Связь с историей доставок (One-to-Many)
    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        "WebhookDelivery",
        back_populates="subscription",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<WebhookSubscription(id={self.id}, name='{self.name}', event={self.event_type.value})>"


class WebhookDelivery(Base):
    """
    История доставки webhook-уведомлений.
    Хранит информацию о каждой попытке отправки:
    payload, статус ответа, время выполнения.
    """

    __tablename__ = "webhook_deliveries"

    # Первичный ключ
    id: Mapped[int] = mapped_column(primary_key=True)

    # Внешний ключ на подписку
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"),
        index=True,
    )

    # Статус доставки
    status: Mapped[DeliveryStatus] = mapped_column(
        String(20),
        default=DeliveryStatus.PENDING,
        index=True,
    )

    # Тело запроса (JSON с данными о событии)
    request_body: Mapped[str] = mapped_column(Text)

    # HTTP-статус ответа (200, 404, 500 и т.д.)
    response_status: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Тело ответа (для отладки ошибок)
    response_body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Сообщение об ошибке (timeout, connection refused и т.д.)
    error_message: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )

    # Номер попытки (1, 2, 3...)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)

    # Время выполнения запроса в миллисекундах
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Когда была попытка
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Связь с подпиской (Many-to-One)
    subscription: Mapped["WebhookSubscription"] = relationship(
        "WebhookSubscription",
        back_populates="deliveries",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<WebhookDelivery(id={self.id}, status={self.status.value}, attempt={self.attempt_number})>"

