import asyncio
from decimal import Decimal

from loguru import logger

from ..celery_app import celery_app
from ..core.database import async_session_factory
from ..data.models.product import ProductStatus
from ..domain.services.batch_service import BatchService
from ..domain.services.product_service import ProductService

# Размер чанка для обработки кодов порциями
CHUNK_SIZE = 500


async def _aggregate_products(
    task: celery_app.Task,
    batch_id: int,
    codes: list[str],
) -> dict[str, object]:
    """
    Асинхронная логика агрегации.

    Разбивает коды на чанки, обновляет статус каждого чанка,
    отправляет прогресс в Celery и обновляет actual_quantity партии.
    """
    total = len(codes)
    processed = 0

    async with async_session_factory() as session:
        batch_service = BatchService(session)
        product_service = ProductService(session)

        # Проверяем, что партия существует
        batch = await batch_service.get_by_id(batch_id)
        logger.info(
            "Агрегация: партия {} ({}), кодов: {}",
            batch.number,
            batch_id,
            total,
        )

        # Обрабатываем коды чанками
        for i in range(0, total, CHUNK_SIZE):
            chunk = codes[i : i + CHUNK_SIZE]

            updated = await product_service.bulk_update_status(
                codes=chunk,
                new_status=ProductStatus.AGGREGATED,
            )

            processed += updated
            progress = int((i + len(chunk)) / total * 100)

            # Обновляем прогресс в Celery (виден через AsyncResult.info)
            task.update_state(
                state="STARTED",
                meta={"progress": progress, "processed": processed},
            )

            logger.debug(
                "Агрегация: чанк {}/{}, обновлено: {}",
                i // CHUNK_SIZE + 1,
                (total + CHUNK_SIZE - 1) // CHUNK_SIZE,
                updated,
            )

        # Обновляем фактическое количество в партии
        await batch_service.update(
            batch_id,
            actual_quantity=batch.actual_quantity + Decimal(processed),
        )

    logger.info(
        "Агрегация завершена: партия {}, обработано {}/{}",
        batch_id,
        processed,
        total,
    )

    return {
        "batch_id": batch_id,
        "total_codes": total,
        "processed": processed,
    }


@celery_app.task(
    bind=True,
    name="src.tasks.aggregation.aggregate_products_task",
    max_retries=3,
    default_retry_delay=10,
)
def aggregate_products_task(
    self: celery_app.Task,
    batch_id: int,
    codes: list[str],
) -> dict[str, object]:
    """
    Celery-задача массовой агрегации продукции.

    Args:
        batch_id: ID партии
        codes: Список кодов продукции для агрегации (до 10 000)

    Returns:
        Словарь с результатами: batch_id, total_codes, processed
    """
    try:
        result: dict[str, object] = asyncio.run(_aggregate_products(self, batch_id, codes))
        return result
    except Exception as exc:
        logger.error("Ошибка агрегации для партии {}: {}", batch_id, exc)
        raise self.retry(exc=exc) from exc
