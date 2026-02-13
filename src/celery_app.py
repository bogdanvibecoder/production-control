from celery import Celery
from kombu import Exchange, Queue

from .core.config import settings

# ---------------------------------------------------------------------------
# Создание экземпляра Celery
# ---------------------------------------------------------------------------
# broker  — RabbitMQ (очередь сообщений, передаёт задачи воркерам)
# backend — Redis (хранит результаты выполнения задач)
celery_app = Celery(
    "production_control",
    broker=settings.rabbitmq.url,
    backend=settings.redis.url,
)

# ---------------------------------------------------------------------------
# Очереди и маршрутизация
# ---------------------------------------------------------------------------
# Три очереди с разным приоритетом:
#   default    — обычные задачи (агрегация, webhooks)
#   reports    — генерация отчётов (тяжёлые, могут занимать время)
#   imports    — импорт/экспорт файлов (I/O-bound)
default_exchange = Exchange("default", type="direct")

task_queues: tuple[Queue, ...] = (
    Queue("default", default_exchange, routing_key="default"),
    Queue("reports", default_exchange, routing_key="reports"),
    Queue("imports", default_exchange, routing_key="imports"),
)

# Маршруты: какая задача идёт в какую очередь
task_routes: dict[str, dict[str, str]] = {
    "src.tasks.reports.*": {"queue": "reports", "routing_key": "reports"},
    "src.tasks.imports.*": {"queue": "imports", "routing_key": "imports"},
    "src.tasks.exports.*": {"queue": "imports", "routing_key": "imports"},
}

# ---------------------------------------------------------------------------
# Конфигурация Celery
# ---------------------------------------------------------------------------
celery_app.conf.update(
    # --- Очереди ---
    task_queues=task_queues,
    task_routes=task_routes,
    task_default_queue=settings.celery.task_default_queue,
    task_default_exchange="default",
    task_default_routing_key="default",
    # --- Сериализация ---
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # --- Часовой пояс ---
    timezone="UTC",
    enable_utc=True,
    # --- Надёжность ---
    task_acks_late=settings.celery.task_acks_late,
    task_reject_on_worker_lost=settings.celery.task_reject_on_worker_lost,
    worker_prefetch_multiplier=settings.celery.worker_prefetch_multiplier,
    # --- Результаты ---
    result_expires=settings.celery.result_expires,
    result_extended=True,
    # --- Retry-политика при потере соединения с брокером ---
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "max_retries": 5,
        "interval_start": 1,
        "interval_step": 2,
        "interval_max": 30,
    },
)

# ---------------------------------------------------------------------------
# Автообнаружение задач
# ---------------------------------------------------------------------------
# Celery просканирует указанные пакеты и зарегистрирует все @celery_app.task
celery_app.autodiscover_tasks(
    [
        "src.tasks.aggregation",
        "src.tasks.reports",
        "src.tasks.imports",
        "src.tasks.exports",
        "src.tasks.webhooks",
        "src.tasks.scheduled",
    ]
)

# ---------------------------------------------------------------------------
# Расписание Celery Beat (периодические задачи)
# ---------------------------------------------------------------------------
celery_app.conf.beat_schedule = {
    # Очистка просроченных результатов задач — каждый час
    "cleanup-expired-results": {
        "task": "src.tasks.scheduled.cleanup_expired_results",
        "schedule": 3600.0,
    },
    # Отправка дневного отчёта — каждый день в 06:00 UTC
    "daily-report": {
        "task": "src.tasks.scheduled.generate_daily_report",
        "schedule": {
            "__type__": "crontab",
            "hour": 6,
            "minute": 0,
        },
    },
    # Проверка зависших партий — каждые 30 минут
    "check-stale-batches": {
        "task": "src.tasks.scheduled.check_stale_batches",
        "schedule": 1800.0,
    },
}
