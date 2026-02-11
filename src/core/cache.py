import json
from collections.abc import Callable
from functools import wraps
from typing import Any

from redis.asyncio import Redis  # type: ignore[import-untyped]

from .config import settings

# === Redis-клиент (singleton) ===

redis_client: Redis = Redis.from_url(
    settings.redis.url,
    decode_responses=True,
)


async def get_redis() -> Redis:
    """
    Зависимость FastAPI для получения Redis-клиента.

    Использование:
        @router.get("/")
        async def handler(redis: Redis = Depends(get_redis)):
            await redis.get("key")
    """
    return redis_client


# === Базовые операции ===


async def cache_get(key: str) -> Any | None:
    """Получить значение из кэша. Возвращает None если ключ не найден."""
    value = await redis_client.get(key)
    if value is None:
        return None
    return json.loads(value)


async def cache_set(
    key: str,
    value: Any,
    ttl: int = 300,
) -> None:
    """
    Записать значение в кэш.

    Args:
        key: ключ кэша
        value: значение (сериализуется в JSON)
        ttl: время жизни в секундах (по умолчанию 5 минут)
    """
    await redis_client.set(key, json.dumps(value, default=str), ex=ttl)


async def cache_delete(key: str) -> None:
    """Удалить ключ из кэша."""
    await redis_client.delete(key)


async def cache_delete_pattern(pattern: str) -> None:
    """
    Удалить все ключи по паттерну (например, 'batches:*').

    Используется для инвалидации группы ключей.
    """
    cursor: int = 0
    while True:
        cursor, keys = await redis_client.scan(cursor=cursor, match=pattern, count=100)
        if keys:
            await redis_client.delete(*keys)
        if cursor == 0:
            break


# === Декоратор кэширования ===


def cached(
    prefix: str,
    ttl: int = 300,
    key_builder: Callable[..., str] | None = None,
) -> Callable:
    """
    Декоратор для кэширования результатов async-функций.

    Args:
        prefix: префикс ключа (например, 'batches', 'analytics')
        ttl: время жизни кэша в секундах (по умолчанию 5 минут)
        key_builder: кастомная функция для построения ключа.
                     Если None — ключ строится из аргументов.

    Пример:
        @cached(prefix="analytics", ttl=60)
        async def get_batch_summary(self):
            ...

        @cached(prefix="batches", key_builder=lambda batch_id: str(batch_id))
        async def get_by_id(self, batch_id: int):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Построение ключа
            if key_builder is not None:
                # Пропускаем self (args[0]) если метод класса
                func_args = args[1:] if args else args
                cache_key = f"{prefix}:{key_builder(*func_args, **kwargs)}"
            else:
                # Автоключ из всех аргументов (кроме self)
                func_args = args[1:] if args else args
                parts = [str(a) for a in func_args]
                parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                suffix = ":".join(parts) if parts else "all"
                cache_key = f"{prefix}:{suffix}"

            # Проверяем кэш
            cached_value = await cache_get(cache_key)
            if cached_value is not None:
                return cached_value

            # Вызываем оригинальную функцию
            result = await func(*args, **kwargs)

            # Сохраняем в кэш
            await cache_set(cache_key, result, ttl=ttl)

            return result

        return wrapper

    return decorator
