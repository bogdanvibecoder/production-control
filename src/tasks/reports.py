import asyncio
import json
from datetime import datetime

from loguru import logger

from ..celery_app import celery_app
from ..core.config import settings
from ..core.database import async_session_factory
from ..domain.services.analytics_service import AnalyticsService
from ..storage.minio_service import get_presigned_url, upload_file
from ..utils.excel_generator import generate_report as generate_excel_report
from ..utils.pdf_generator import generate_report as generate_pdf_report


async def _generate_production_report(
    task: celery_app.Task,
    date_from: str,
    date_to: str,
    work_center_id: int | None,
    report_format: str,
) -> dict[str, object]:
    """
    Асинхронная логика генерации отчёта.

    1. Собирает аналитику из БД
    2. Формирует файл (JSON-заглушка, Excel/PDF — в Фазе 11)
    3. Загружает в MinIO
    4. Возвращает presigned URL для скачивания
    """
    task.update_state(state="STARTED", meta={"progress": 10})

    # --- Шаг 1: Собираем данные ---
    dt_from = datetime.fromisoformat(date_from)
    dt_to = datetime.fromisoformat(date_to)

    async with async_session_factory() as session:
        analytics = AnalyticsService(session)
        report_data = await analytics.get_production_report(
            dt_from,
            dt_to,
            work_center_id=work_center_id,
        )

    task.update_state(state="STARTED", meta={"progress": 50})
    logger.info(
        "Отчёт: данные собраны за период {} — {}",
        date_from,
        date_to,
    )

    # --- Шаг 2: Формируем файл ---
    if report_format == "xlsx":
        file_bytes = generate_excel_report(report_data)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        extension = "xlsx"
    elif report_format == "pdf":
        file_bytes = generate_pdf_report(report_data)
        content_type = "application/pdf"
        extension = "pdf"
    else:
        serializable = _make_serializable(report_data)
        file_bytes = json.dumps(serializable, ensure_ascii=False, indent=2).encode("utf-8")
        content_type = "application/json"
        extension = "json"

    task.update_state(state="STARTED", meta={"progress": 80})

    # --- Шаг 3: Загружаем в MinIO ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    object_name = f"reports/{dt_from.strftime('%Y-%m')}/report_{timestamp}.{extension}"

    upload_file(
        bucket_name=settings.minio.bucket_reports,
        object_name=object_name,
        data=file_bytes,
        content_type=content_type,
    )

    task.update_state(state="STARTED", meta={"progress": 95})

    # --- Шаг 4: Генерируем presigned URL ---
    download_filename = (
        f"production_report_{dt_from.strftime('%Y%m%d')}_{dt_to.strftime('%Y%m%d')}.{extension}"
    )

    url = get_presigned_url(
        bucket_name=settings.minio.bucket_reports,
        object_name=object_name,
        filename=download_filename,
    )

    logger.info("Отчёт сгенерирован: {}", object_name)

    return {
        "object_name": object_name,
        "download_url": url,
        "format": report_format,
        "period": {"date_from": date_from, "date_to": date_to},
    }


def _make_serializable(data: dict[str, object]) -> dict[str, object]:
    """Преобразовать не-JSON-сериализуемые типы (Decimal, datetime)."""
    result: dict[str, object] = {}
    for key, value in data.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif hasattr(value, "__str__") and type(value).__name__ == "Decimal":
            result[key] = str(value)
        else:
            result[key] = value
    return result


@celery_app.task(
    bind=True,
    name="src.tasks.reports.generate_report_task",
    max_retries=2,
    default_retry_delay=30,
    queue="reports",
)
def generate_report_task(
    self: celery_app.Task,
    date_from: str,
    date_to: str,
    work_center_id: int | None = None,
    report_format: str = "xlsx",
) -> dict[str, object]:
    """
    Celery-задача генерации производственного отчёта.

    Args:
        date_from: Начало периода (ISO-формат)
        date_to: Конец периода (ISO-формат)
        work_center_id: ID рабочего центра (опционально, None = все)
        report_format: Формат файла: "xlsx", "pdf" или "json"

    Returns:
        Словарь с object_name, download_url, format, period
    """
    try:
        result: dict[str, object] = asyncio.run(
            _generate_production_report(self, date_from, date_to, work_center_id, report_format)
        )
        return result
    except Exception as exc:
        logger.error("Ошибка генерации отчёта: {}", exc)
        raise self.retry(exc=exc) from exc
