import asyncio
import time

import httpx
from loguru import logger

from ..celery_app import celery_app
from ..core.database import async_session_factory
from ..data.models.webhook import DeliveryStatus, WebhookDelivery
from ..data.repositories.webhook_repository import WebhookRepository
from ..utils.hmac_utils import sign as hmac_sign

# Таймаут HTTP-запроса к внешнему сервису (секунды)
HTTP_TIMEOUT = 10


async def _send_single_webhook(delivery_id: int) -> dict[str, object]:
    """
    Асинхронная логика отправки одного webhook.

    1. Загружает delivery + subscription из БД
    2. Подписывает payload HMAC-SHA256
    3. Отправляет POST-запрос на target_url
    4. Обновляет статус доставки в БД
    """
    async with async_session_factory() as session:
        repo = WebhookRepository(session)

        # --- Загружаем delivery (с subscription через lazy="joined") ---
        delivery = await session.get(WebhookDelivery, delivery_id)

        if delivery is None:
            logger.error("Webhook delivery {} не найден", delivery_id)
            return {"delivery_id": delivery_id, "status": "not_found"}

        subscription = delivery.subscription

        if not subscription.is_active:
            logger.info(
                "Подписка {} неактивна, пропускаем delivery {}",
                subscription.id,
                delivery_id,
            )
            await repo.update_delivery(
                delivery_id,
                status=DeliveryStatus.FAILED,
                error_message="Subscription is inactive",
            )
            await session.commit()
            return {"delivery_id": delivery_id, "status": "skipped"}

        # --- HMAC-подпись ---
        signature = hmac_sign(subscription.secret, delivery.request_body)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": f"sha256={signature}",
            "X-Webhook-Event": subscription.event_type.value,
            "X-Delivery-Id": str(delivery_id),
        }

        # --- Отправка HTTP POST ---
        start_time = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.post(
                    subscription.target_url,
                    content=delivery.request_body,
                    headers=headers,
                )

            duration_ms = int((time.monotonic() - start_time) * 1000)

            # Ответ 2xx — успех
            if response.is_success:
                await repo.update_delivery(
                    delivery_id,
                    status=DeliveryStatus.SUCCESS,
                    response_status=response.status_code,
                    response_body=response.text[:2048],
                    duration_ms=duration_ms,
                )
                await session.commit()

                logger.info(
                    "Webhook доставлен: delivery={}, url={}, status={}",
                    delivery_id,
                    subscription.target_url,
                    response.status_code,
                )
                return {
                    "delivery_id": delivery_id,
                    "status": "success",
                    "http_status": response.status_code,
                    "duration_ms": duration_ms,
                }

            # Ответ 4xx/5xx — ошибка
            await repo.update_delivery(
                delivery_id,
                status=DeliveryStatus.FAILED,
                response_status=response.status_code,
                response_body=response.text[:2048],
                duration_ms=duration_ms,
            )
            await session.commit()

            logger.warning(
                "Webhook ошибка: delivery={}, url={}, status={}",
                delivery_id,
                subscription.target_url,
                response.status_code,
            )
            return {
                "delivery_id": delivery_id,
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
            }

        except Exception as exc:
            duration_ms = int((time.monotonic() - start_time) * 1000)

            await repo.update_delivery(
                delivery_id,
                status=DeliveryStatus.FAILED,
                error_message=str(exc)[:1024],
                duration_ms=duration_ms,
            )
            await session.commit()

            logger.error(
                "Webhook сетевая ошибка: delivery={}, url={}, error={}",
                delivery_id,
                subscription.target_url,
                exc,
            )
            raise


async def _process_pending_webhooks() -> dict[str, object]:
    """Загрузить pending-доставки и поставить задачу на каждую."""
    async with async_session_factory() as session:
        repo = WebhookRepository(session)
        pending = await repo.get_pending_deliveries(limit=100)

    delivery_ids = [d.id for d in pending]

    for delivery_id in delivery_ids:
        send_webhook_task.delay(delivery_id)

    logger.info("Поставлено {} webhook-задач в очередь", len(delivery_ids))
    return {"dispatched": len(delivery_ids), "delivery_ids": delivery_ids}


# ---------------------------------------------------------------------------
# Celery-задачи
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="src.tasks.webhooks.send_webhook_task",
    max_retries=5,
    default_retry_delay=30,
    autoretry_for=(httpx.HTTPError, OSError),
    retry_backoff=True,
    retry_backoff_max=300,
)
def send_webhook_task(
    self: celery_app.Task,
    delivery_id: int,
) -> dict[str, object]:
    """
    Celery-задача отправки одного webhook.

    Args:
        delivery_id: ID записи WebhookDelivery

    Returns:
        Словарь с delivery_id, status, http_status, duration_ms
    """
    try:
        result: dict[str, object] = asyncio.run(_send_single_webhook(delivery_id))
        return result
    except (httpx.HTTPError, OSError):
        # autoretry_for перехватит и поставит retry автоматически
        raise
    except Exception as exc:
        logger.error("Webhook задача ошибка: delivery={}, {}", delivery_id, exc)
        raise self.retry(exc=exc) from exc


@celery_app.task(
    name="src.tasks.webhooks.dispatch_pending_webhooks",
)
def dispatch_pending_webhooks() -> dict[str, object]:
    """
    Celery-задача: найти все pending-доставки и поставить их в очередь.

    Вызывается из Celery Beat или вручную для обработки накопившихся
    webhook-доставок.
    """
    result: dict[str, object] = asyncio.run(_process_pending_webhooks())
    return result
