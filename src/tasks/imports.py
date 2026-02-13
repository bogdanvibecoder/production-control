import asyncio
import csv
import io
from decimal import Decimal

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from ..celery_app import celery_app
from ..core.config import settings
from ..core.database import async_session_factory
from ..data.models.product import Product
from ..domain.services.batch_service import BatchService
from ..storage.minio_service import download_file

# Размер чанка для bulk-вставки
CHUNK_SIZE = 500


async def _import_products(
    task: celery_app.Task,
    batch_id: int,
    file_name: str,
) -> dict[str, object]:
    """
    Асинхронная логика импорта продукции из файла.

    1. Скачивает файл из MinIO
    2. Парсит строки (CSV / Excel)
    3. Создаёт записи Product в БД чанками
    4. Обновляет actual_quantity партии
    """
    task.update_state(state="STARTED", meta={"progress": 5})

    # --- Шаг 1: Скачиваем файл ---
    file_bytes = download_file(
        bucket_name=settings.minio.bucket_imports,
        object_name=file_name,
    )
    logger.info("Импорт: файл скачан из MinIO — {}", file_name)

    task.update_state(state="STARTED", meta={"progress": 15})

    # --- Шаг 2: Парсим строки ---
    rows = _parse_file(file_name, file_bytes)
    total = len(rows)

    if total == 0:
        logger.warning("Импорт: файл {} не содержит данных", file_name)
        return {
            "batch_id": batch_id,
            "file_name": file_name,
            "total_rows": 0,
            "imported": 0,
            "skipped": 0,
        }

    logger.info("Импорт: распознано {} строк из {}", total, file_name)
    task.update_state(state="STARTED", meta={"progress": 25})

    # --- Шаг 3: Создаём записи в БД чанками ---
    imported = 0
    skipped = 0

    async with async_session_factory() as session:
        batch_service = BatchService(session)

        # Проверяем, что партия существует
        batch = await batch_service.get_by_id(batch_id)

        for i in range(0, total, CHUNK_SIZE):
            chunk = rows[i : i + CHUNK_SIZE]
            chunk_imported, chunk_skipped = await _insert_chunk(session, batch_id, chunk)
            imported += chunk_imported
            skipped += chunk_skipped

            # Прогресс: 25% уже прошло, оставшиеся 65% делим на чанки
            progress = 25 + int((i + len(chunk)) / total * 65)
            task.update_state(
                state="STARTED",
                meta={
                    "progress": progress,
                    "imported": imported,
                    "skipped": skipped,
                },
            )

            logger.debug(
                "Импорт: чанк {}/{}, imported={}, skipped={}",
                i // CHUNK_SIZE + 1,
                (total + CHUNK_SIZE - 1) // CHUNK_SIZE,
                chunk_imported,
                chunk_skipped,
            )

        # --- Шаг 4: Обновляем actual_quantity партии ---
        await batch_service.update(
            batch_id,
            actual_quantity=batch.actual_quantity + Decimal(imported),
        )

    logger.info(
        "Импорт завершён: партия {}, imported={}, skipped={}",
        batch_id,
        imported,
        skipped,
    )

    return {
        "batch_id": batch_id,
        "file_name": file_name,
        "total_rows": total,
        "imported": imported,
        "skipped": skipped,
    }


def _parse_file(file_name: str, file_bytes: bytes) -> list[dict[str, str]]:
    """
    Парсинг файла в список словарей.

    Поддерживает CSV. Для Excel (xlsx) — заглушка до Фазы 11
    (будет вызов excel_parser.parse_products).

    Ожидаемые колонки CSV: code, product_type, extra_data (опционально)
    """
    if file_name.endswith(".csv"):
        return _parse_csv(file_bytes)

    if file_name.endswith((".xlsx", ".xls")):
        # Заглушка: в Фазе 11 заменить на excel_parser.parse_products(file_bytes)
        logger.warning("Excel-парсинг ещё не реализован, файл: {}", file_name)
        return []

    logger.error("Неподдерживаемый формат файла: {}", file_name)
    return []


def _parse_csv(file_bytes: bytes) -> list[dict[str, str]]:
    """Парсинг CSV-файла."""
    text = file_bytes.decode("utf-8-sig")  # utf-8-sig убирает BOM
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


async def _insert_chunk(
    session: AsyncSession,
    batch_id: int,
    rows: list[dict[str, str]],
) -> tuple[int, int]:
    """
    Вставить чанк записей в БД.

    Returns:
        (imported, skipped) — количество вставленных и пропущенных строк
    """
    imported = 0
    skipped = 0

    for row in rows:
        code = row.get("code", "").strip()
        product_type = row.get("product_type", "").strip()

        if not code or not product_type:
            skipped += 1
            continue

        product = Product(
            code=code,
            batch_id=batch_id,
            product_type=product_type,
            extra_data=row.get("extra_data"),
        )
        session.add(product)
        imported += 1

    try:
        await session.flush()
    except Exception as exc:
        await session.rollback()
        logger.error("Ошибка вставки чанка: {}", exc)
        skipped += imported
        imported = 0

    return imported, skipped


@celery_app.task(
    bind=True,
    name="src.tasks.imports.import_products_task",
    max_retries=3,
    default_retry_delay=15,
    queue="imports",
)
def import_products_task(
    self: celery_app.Task,
    batch_id: int,
    file_name: str,
) -> dict[str, object]:
    """
    Celery-задача импорта продукции из файла.

    Args:
        batch_id: ID партии, в которую импортируется продукция
        file_name: Имя файла в MinIO (бакет imports)

    Returns:
        Словарь с результатами: batch_id, file_name, total_rows, imported, skipped
    """
    try:
        result: dict[str, object] = asyncio.run(_import_products(self, batch_id, file_name))
        return result
    except Exception as exc:
        logger.error(
            "Ошибка импорта из {} для партии {}: {}",
            file_name,
            batch_id,
            exc,
        )
        raise self.retry(exc=exc) from exc
