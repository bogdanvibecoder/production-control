"""
Фикстуры pytest для unit- и integration-тестов.

Используем async SQLite (aiosqlite) вместо PostgreSQL,
чтобы тесты работали без внешних сервисов.
Каждый тест получает чистую БД с откатом транзакции.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.database import Base, get_async_session
from src.data.models.batch import Batch, BatchStatus
from src.data.models.product import Product, ProductStatus
from src.data.models.webhook import (
    DeliveryStatus,
    WebhookDelivery,
    WebhookEvent,
    WebhookSubscription,
)
from src.data.models.work_center import WorkCenter
from src.main import app

# ---------------------------------------------------------------------------
# Тестовый движок (async SQLite in-memory)
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
)

TestSessionFactory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# SQLite совместимость: конвертация строк в enum при загрузке из БД.
# PostgreSQL хранит enum нативно, а SQLite — как строки.
# ---------------------------------------------------------------------------

_ENUM_FIELDS: list[tuple[type, str, type]] = [
    (Batch, "status", BatchStatus),
    (Product, "status", ProductStatus),
    (WebhookSubscription, "event_type", WebhookEvent),
    (WebhookDelivery, "status", DeliveryStatus),
]

for _model, _field, _enum_cls in _ENUM_FIELDS:

    def _make_listener(field: str, enum_cls: type):  # noqa: E303
        def _convert_enum(target: object, *_args: object) -> None:
            val = getattr(target, field, None)
            if isinstance(val, str) and not isinstance(val, enum_cls):
                setattr(target, field, enum_cls(val))

        return _convert_enum

    event.listen(_model, "load", _make_listener(_field, _enum_cls))
    event.listen(_model, "refresh", _make_listener(_field, _enum_cls))


# ---------------------------------------------------------------------------
# Основные фикстуры
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def _setup_db() -> AsyncGenerator[None, None]:
    """Создаёт таблицы перед каждым тестом, удаляет после."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """Асинхронная сессия БД для тестов."""
    async with TestSessionFactory() as session:
        yield session


@pytest.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTP-клиент для интеграционных тестов.

    Подменяет зависимость get_async_session на тестовую сессию,
    чтобы API-эндпоинты работали с in-memory SQLite.
    """

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_async_session] = _override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=True
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Фабрики тестовых данных
# ---------------------------------------------------------------------------


@pytest.fixture
async def work_center(session: AsyncSession) -> WorkCenter:
    """Создаёт тестовый рабочий центр."""
    wc = WorkCenter(
        code="LINE-01",
        name="Линия розлива №1",
        is_active=True,
    )
    session.add(wc)
    await session.flush()
    await session.refresh(wc)
    return wc


@pytest.fixture
async def batch(session: AsyncSession, work_center: WorkCenter) -> Batch:
    """Создаёт тестовую партию (статус PLANNED)."""
    b = Batch(
        number="B-2026-001",
        work_center_id=work_center.id,
        shift_date=datetime(2026, 2, 15, tzinfo=UTC),
        shift_number=1,
        status=BatchStatus.PLANNED,
        planned_quantity=Decimal("100.000"),
        actual_quantity=Decimal("0.000"),
    )
    session.add(b)
    await session.flush()
    await session.refresh(b)
    return b


@pytest.fixture
async def batch_in_progress(session: AsyncSession, work_center: WorkCenter) -> Batch:
    """Создаёт тестовую партию (статус IN_PROGRESS)."""
    b = Batch(
        number="B-2026-002",
        work_center_id=work_center.id,
        shift_date=datetime(2026, 2, 15, tzinfo=UTC),
        shift_number=2,
        status=BatchStatus.IN_PROGRESS,
        planned_quantity=Decimal("200.000"),
        actual_quantity=Decimal("50.000"),
        started_at=datetime(2026, 2, 15, 8, 0, tzinfo=UTC),
    )
    session.add(b)
    await session.flush()
    await session.refresh(b)
    return b


@pytest.fixture
async def product(session: AsyncSession, batch: Batch) -> Product:
    """Создаёт тестовую единицу продукции (статус PRODUCED)."""
    p = Product(
        code="PRD-001",
        batch_id=batch.id,
        product_type="bottle",
        status=ProductStatus.PRODUCED,
    )
    session.add(p)
    await session.flush()
    await session.refresh(p)
    return p


@pytest.fixture
async def product_aggregated(session: AsyncSession, batch: Batch) -> Product:
    """Создаёт тестовую единицу продукции (статус AGGREGATED)."""
    p = Product(
        code="PRD-002",
        batch_id=batch.id,
        product_type="bottle",
        status=ProductStatus.AGGREGATED,
    )
    session.add(p)
    await session.flush()
    await session.refresh(p)
    return p


@pytest.fixture
async def webhook_subscription(session: AsyncSession) -> WebhookSubscription:
    """Создаёт тестовую webhook-подписку."""
    sub = WebhookSubscription(
        name="Тестовый webhook",
        target_url="https://example.com/webhook",
        event_type=WebhookEvent.BATCH_COMPLETED,
        secret="test-secret-key-1234567890",
        is_active=True,
    )
    session.add(sub)
    await session.flush()
    await session.refresh(sub)
    return sub


@pytest.fixture
async def webhook_delivery(
    session: AsyncSession,
    webhook_subscription: WebhookSubscription,
) -> WebhookDelivery:
    """Создаёт тестовую запись о доставке webhook."""
    delivery = WebhookDelivery(
        subscription_id=webhook_subscription.id,
        status=DeliveryStatus.PENDING,
        request_body='{"event": "batch.completed", "batch_id": 1}',
    )
    session.add(delivery)
    await session.flush()
    await session.refresh(delivery)
    return delivery
