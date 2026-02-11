"""
Скрипт инициализации MinIO.

Создаёт все необходимые бакеты при первом запуске.
Безопасен для повторного вызова (идемпотентный).

Использование:
    python -m scripts.init_minio

Или из корня проекта:
    poetry run python -m scripts.init_minio
"""

import sys
import time

from loguru import logger
from minio.error import S3Error
from urllib3.exceptions import MaxRetryError

from src.core.config import settings
from src.storage.minio_service import ensure_all_buckets, minio_client

# Максимальное количество попыток подключения
MAX_RETRIES = 10
# Задержка между попытками (секунды)
RETRY_DELAY = 3


def wait_for_minio() -> bool:
    """
    Дождаться доступности MinIO.

    MinIO в Docker может стартовать позже, чем скрипт.
    Пробуем подключиться MAX_RETRIES раз с паузой RETRY_DELAY секунд.

    Returns:
        True если MinIO доступен, False если все попытки исчерпаны
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            minio_client.list_buckets()
            logger.info("MinIO доступен (попытка {}/{})", attempt, MAX_RETRIES)
            return True
        except (S3Error, MaxRetryError, ConnectionError, OSError) as e:
            logger.warning(
                "MinIO недоступен (попытка {}/{}): {}",
                attempt,
                MAX_RETRIES,
                e,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    return False


def main() -> None:
    """Точка входа скрипта."""
    logger.info(
        "Инициализация MinIO: endpoint={}",
        settings.minio.endpoint,
    )

    # Шаг 1: ждём доступности MinIO
    if not wait_for_minio():
        logger.error(
            "MinIO недоступен после {} попыток. Проверьте подключение: {}",
            MAX_RETRIES,
            settings.minio.endpoint,
        )
        sys.exit(1)

    # Шаг 2: создаём бакеты
    try:
        ensure_all_buckets()
        logger.info("Инициализация MinIO завершена успешно")
    except S3Error as e:
        logger.error("Ошибка при создании бакетов: {}", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
