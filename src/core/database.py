from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from .config import settings

engine = create_async_engine(
    url=settings.db.async_dsn,
    echo=settings.db.echo,
    pool_size=5,
    max_overflow=10
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """
    Базовый класс для всех ORM-моделей.
    Все модели наследуются от этого класса.
    """
    pass


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Асинхронный генератор сессий для FastAPI Dependency Injection.

    Использование в роутерах:
        @router.get("/items")
        async def get_items(session: AsyncSession = Depends(get_async_session)):
            ...
    """
    async with async_session_factory() as session:
        yield session