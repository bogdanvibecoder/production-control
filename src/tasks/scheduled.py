import asyncio
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import and_, delete, func, select

from ..celery_app import celery_app
from ..core.database import async_session_factory
from ..data.models.batch import Batch, BatchStatus
from ..data.models.webhook import DeliveryStatus, WebhookDelivery
from .reports import generate_report_task

# Порог «зависшей» партии — если IN_PROGRESS дольше этого, считаем stale
STALE_BATCH_HOURS = 24

# Хранить историю webhook-доставок не дольше этого
DELIVERY_RETENTION_DAYS = 30


# ---------------------------------------------------------------------------
# 1. Очистка устаревших webhook-доставок
# ---------------------------------------------------------------------------


async def _cleanup_expired_results() -> dict[str, object]:
    """
    Удаляет webhook-доставки старше DELIVERY_RETENTION_DAYS.

    Удаляются только завершённые (SUCCESS / FAILED), чтобы не потерять
    pending/retrying доставки.
    """
    cutoff = datetime.now(UTC) - timedelta(days=DELIVERY_RETENTION_DAYS)

    async with async_session_factory() as session:
        stmt = delete(WebhookDelivery).where(
            and_(
                WebhookDelivery.attempted_at < cutoff,
                WebhookDelivery.status.in_([DeliveryStatus.SUCCESS, DeliveryStatus.FAILED]),
            )
        )
        result = await session.execute(stmt)
        deleted_count: int = result.rowcount  # type: ignore[attr-defined]
        await session.commit()

    logger.info(
        "Очистка: удалено {} устаревших webhook-доставок (старше {} дней)",
        deleted_count,
        DELIVERY_RETENTION_DAYS,
    )
    return {"deleted": deleted_count, "cutoff": cutoff.isoformat()}


@celery_app.task(name="src.tasks.scheduled.cleanup_expired_results")
def cleanup_expired_results() -> dict[str, object]:
    """
    Периодическая задача: очистка устаревших webhook-доставок.
    Расписание: каждый час (настроено в celery_app.py beat_schedule).
    """
    result: dict[str, object] = asyncio.run(_cleanup_expired_results())
    return result


# ---------------------------------------------------------------------------
# 2. Генерация дневного отчёта
# ---------------------------------------------------------------------------


async def _generate_daily_report() -> dict[str, object]:
    """
    Генерирует отчёт за вчерашний день.

    Ставит задачу generate_report_task из модуля reports,
    чтобы не дублировать логику генерации.
    """
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    date_from = datetime(yesterday.year, yesterday.month, yesterday.day, tzinfo=UTC)
    date_to = date_from + timedelta(days=1)

    # Проверяем, были ли вообще партии за вчера
    async with async_session_factory() as session:
        stmt = (
            select(func.count())
            .select_from(Batch)
            .where(
                and_(
                    Batch.shift_date >= date_from,
                    Batch.shift_date < date_to,
                )
            )
        )
        count: int = await session.scalar(stmt) or 0

    if count == 0:
        logger.info("Дневной отчёт: за {} нет партий, пропускаем", yesterday)
        return {"date": yesterday.isoformat(), "status": "skipped", "reason": "no batches"}

    # Ставим задачу генерации отчёта
    task_result = generate_report_task.delay(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        report_format="xlsx",
    )

    logger.info(
        "Дневной отчёт за {}: задача {} поставлена в очередь",
        yesterday,
        task_result.id,
    )
    return {
        "date": yesterday.isoformat(),
        "status": "dispatched",
        "report_task_id": task_result.id,
    }


@celery_app.task(name="src.tasks.scheduled.generate_daily_report")
def generate_daily_report() -> dict[str, object]:
    """
    Периодическая задача: генерация дневного отчёта.
    Расписание: ежедневно в 06:00 UTC (настроено в celery_app.py beat_schedule).
    """
    result: dict[str, object] = asyncio.run(_generate_daily_report())
    return result


# ---------------------------------------------------------------------------
# 3. Проверка зависших партий
# ---------------------------------------------------------------------------


async def _check_stale_batches() -> dict[str, object]:
    """
    Находит партии в статусе IN_PROGRESS дольше STALE_BATCH_HOURS.

    Не меняет статус автоматически — только логирует и возвращает
    список для мониторинга/алертов.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=STALE_BATCH_HOURS)

    async with async_session_factory() as session:
        stmt = (
            select(Batch)
            .where(
                and_(
                    Batch.status == BatchStatus.IN_PROGRESS,
                    Batch.started_at < cutoff,
                )
            )
            .order_by(Batch.started_at.asc())
        )
        result = await session.scalars(stmt)
        stale_batches = result.all()

    stale_ids = [b.id for b in stale_batches]

    if stale_ids:
        logger.warning(
            "Обнаружено {} зависших партий (IN_PROGRESS > {} ч): {}",
            len(stale_ids),
            STALE_BATCH_HOURS,
            stale_ids,
        )
    else:
        logger.debug("Зависших партий не обнаружено")

    return {
        "stale_count": len(stale_ids),
        "stale_batch_ids": stale_ids,
        "threshold_hours": STALE_BATCH_HOURS,
    }


@celery_app.task(name="src.tasks.scheduled.check_stale_batches")
def check_stale_batches() -> dict[str, object]:
    """
    Периодическая задача: проверка зависших партий.
    Расписание: каждые 30 минут (настроено в celery_app.py beat_schedule).
    """
    result: dict[str, object] = asyncio.run(_check_stale_batches())
    return result
