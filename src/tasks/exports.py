import asyncio
import csv
import io
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import select

from ..celery_app import celery_app
from ..core.config import settings
from ..core.database import async_session_factory
from ..data.models.batch import Batch
from ..data.models.product import Product
from ..storage.minio_service import get_presigned_url, upload_file
from ..utils.excel_generator import generate_export as generate_excel_export

# Лимит выгрузки за один запрос
EXPORT_LIMIT = 50_000


async def _export_data(
    task: celery_app.Task,
    export_format: str,
    date_from: str | None,
    date_to: str | None,
) -> dict[str, object]:
    """
    Асинхронная логика экспорта данных.

    1. Загружает партии и продукцию из БД
    2. Формирует CSV (или Excel — заглушка до Фазы 11)
    3. Загружает файл в MinIO
    4. Возвращает presigned URL для скачивания
    """
    task.update_state(state="STARTED", meta={"progress": 10})

    # --- Шаг 1: Загружаем данные из БД ---
    async with async_session_factory() as session:
        # Строим запрос: продукция + партия (JOIN)
        stmt = (
            select(Product, Batch)
            .join(Batch, Product.batch_id == Batch.id)
            .order_by(Batch.shift_date.desc(), Product.produced_at.desc())
            .limit(EXPORT_LIMIT)
        )

        # Фильтр по датам (если указаны)
        if date_from is not None:
            dt_from = datetime.fromisoformat(date_from)
            stmt = stmt.where(Batch.shift_date >= dt_from)
        if date_to is not None:
            dt_to = datetime.fromisoformat(date_to)
            stmt = stmt.where(Batch.shift_date <= dt_to)

        result = await session.execute(stmt)
        rows = result.all()

    total = len(rows)
    logger.info("Экспорт: загружено {} записей из БД", total)
    task.update_state(state="STARTED", meta={"progress": 40})

    # --- Шаг 2: Формируем файл ---
    if export_format == "csv":
        file_bytes = _build_csv(rows)
        content_type = "text/csv; charset=utf-8"
        extension = "csv"
    else:
        file_bytes = generate_excel_export(rows)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        extension = "xlsx"

    task.update_state(state="STARTED", meta={"progress": 70})

    # --- Шаг 3: Загружаем в MinIO ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    period_suffix = ""
    if date_from:
        period_suffix += f"_from{date_from[:10]}"
    if date_to:
        period_suffix += f"_to{date_to[:10]}"

    object_name = f"exports/export{period_suffix}_{timestamp}.{extension}"

    upload_file(
        bucket_name=settings.minio.bucket_reports,
        object_name=object_name,
        data=file_bytes,
        content_type=content_type,
    )

    task.update_state(state="STARTED", meta={"progress": 90})

    # --- Шаг 4: Presigned URL ---
    download_filename = f"export{period_suffix}.{extension}"

    url = get_presigned_url(
        bucket_name=settings.minio.bucket_reports,
        object_name=object_name,
        filename=download_filename,
    )

    logger.info("Экспорт завершён: {}, {} записей", object_name, total)

    return {
        "object_name": object_name,
        "download_url": url,
        "format": export_format,
        "total_rows": total,
    }


def _build_csv(rows: Sequence[Any]) -> bytes:
    """
    Формирование CSV из результатов запроса (Product + Batch).

    Колонки: batch_number, shift_date, shift_number, status (batch),
             code, product_type, product_status, produced_at, extra_data
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Заголовки
    writer.writerow(
        [
            "batch_number",
            "shift_date",
            "shift_number",
            "batch_status",
            "code",
            "product_type",
            "product_status",
            "produced_at",
            "extra_data",
        ]
    )

    for row in rows:
        product: Product = row[0]
        batch: Batch = row[1]

        writer.writerow(
            [
                batch.number,
                batch.shift_date.isoformat() if batch.shift_date else "",
                batch.shift_number,
                batch.status.value,
                product.code,
                product.product_type,
                product.status.value,
                product.produced_at.isoformat() if product.produced_at else "",
                product.extra_data or "",
            ]
        )

    csv_bytes: bytes = output.getvalue().encode("utf-8-sig")
    return csv_bytes


@celery_app.task(
    bind=True,
    name="src.tasks.exports.export_data_task",
    max_retries=2,
    default_retry_delay=20,
    queue="imports",
)
def export_data_task(
    self: celery_app.Task,
    export_format: str = "xlsx",
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, object]:
    """
    Celery-задача экспорта данных в файл.

    Args:
        export_format: Формат файла ("xlsx" или "csv")
        date_from: Начало диапазона дат (ISO-формат, опционально)
        date_to: Конец диапазона дат (ISO-формат, опционально)

    Returns:
        Словарь с object_name, download_url, format, total_rows
    """
    try:
        result: dict[str, object] = asyncio.run(
            _export_data(self, export_format, date_from, date_to)
        )
        return result
    except Exception as exc:
        logger.error("Ошибка экспорта: {}", exc)
        raise self.retry(exc=exc) from exc
