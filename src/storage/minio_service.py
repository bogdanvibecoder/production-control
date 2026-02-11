from io import BytesIO

from loguru import logger
from minio import Minio
from minio.error import S3Error

from ..core.config import settings

# === MinIO-клиент (singleton) ===

minio_client: Minio = Minio(
    endpoint=settings.minio.endpoint,
    access_key=settings.minio.access_key,
    secret_key=settings.minio.secret_key,
    secure=settings.minio.secure,
)


def _get_client() -> Minio:
    """Получить экземпляр MinIO-клиента."""
    return minio_client


# === Управление бакетами ===


def ensure_bucket(bucket_name: str) -> None:
    """
    Создать бакет, если он ещё не существует.

    Используется при инициализации приложения и в скрипте init_minio.py.
    """
    client = _get_client()
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)
        logger.info("Создан бакет: {}", bucket_name)
    else:
        logger.debug("Бакет уже существует: {}", bucket_name)


def ensure_all_buckets() -> None:
    """Создать все бакеты из конфигурации."""
    ensure_bucket(settings.minio.bucket_reports)
    ensure_bucket(settings.minio.bucket_imports)


# === Загрузка файлов ===


def upload_file(
    bucket_name: str,
    object_name: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """
    Загрузить файл в MinIO.

    Args:
        bucket_name: имя бакета
        object_name: путь/имя объекта в бакете (например, "reports/2026-02/report_123.xlsx")
        data: содержимое файла в байтах
        content_type: MIME-тип файла

    Returns:
        object_name загруженного файла
    """
    client = _get_client()
    stream = BytesIO(data)
    client.put_object(
        bucket_name=bucket_name,
        object_name=object_name,
        data=stream,
        length=len(data),
        content_type=content_type,
    )
    logger.info(
        "Файл загружен: bucket={}, object={}",
        bucket_name,
        object_name,
    )
    return object_name


# === Скачивание файлов ===


def download_file(bucket_name: str, object_name: str) -> bytes:
    """
    Скачать файл из MinIO.

    Args:
        bucket_name: имя бакета
        object_name: путь/имя объекта

    Returns:
        Содержимое файла в байтах

    Raises:
        S3Error: если файл не найден или ошибка доступа
    """
    client = _get_client()
    response = None
    try:
        response = client.get_object(bucket_name, object_name)
        data: bytes = response.read()
        logger.info(
            "Файл скачан: bucket={}, object={}, size={}",
            bucket_name,
            object_name,
            len(data),
        )
        return data
    finally:
        if response is not None:
            response.close()
            response.release_conn()


# === Удаление файлов ===


def delete_file(bucket_name: str, object_name: str) -> None:
    """
    Удалить файл из MinIO.

    Args:
        bucket_name: имя бакета
        object_name: путь/имя объекта
    """
    client = _get_client()
    client.remove_object(bucket_name, object_name)
    logger.info(
        "Файл удалён: bucket={}, object={}",
        bucket_name,
        object_name,
    )


# === Проверка существования ===


def file_exists(bucket_name: str, object_name: str) -> bool:
    """
    Проверить, существует ли файл в MinIO.

    Returns:
        True если файл существует, False если нет
    """
    client = _get_client()
    try:
        client.stat_object(bucket_name, object_name)
        return True
    except S3Error as e:
        if e.code == "NoSuchKey":
            return False
        raise


# === Presigned URLs ===


def get_presigned_url(
    bucket_name: str,
    object_name: str,
    expires: int = 3600,
    filename: str | None = None,
) -> str:
    """
    Сгенерировать presigned URL для скачивания файла.

    Args:
        bucket_name: имя бакета
        object_name: путь/имя объекта
        expires: время жизни ссылки в секундах (по умолчанию 1 час)
        filename: имя файла для Content-Disposition (скачивание с нужным именем)

    Returns:
        Presigned URL
    """
    from datetime import timedelta

    client = _get_client()

    extra_query_params = None
    if filename is not None:
        disposition = f'attachment; filename="{filename}"'
        extra_query_params = {"response-content-disposition": disposition}

    url: str = client.presigned_get_object(
        bucket_name=bucket_name,
        object_name=object_name,
        expires=timedelta(seconds=expires),
        extra_query_params=extra_query_params,
    )
    logger.debug(
        "Presigned URL создан: bucket={}, object={}, expires={}s",
        bucket_name,
        object_name,
        expires,
    )
    return url


# === Список файлов ===


def list_files(
    bucket_name: str,
    prefix: str = "",
    recursive: bool = True,
) -> list[str]:
    """
    Получить список файлов в бакете по префиксу.

    Args:
        bucket_name: имя бакета
        prefix: префикс пути (например, "reports/2026-02/")
        recursive: рекурсивный обход поддиректорий

    Returns:
        Список имён объектов
    """
    client = _get_client()
    objects = client.list_objects(
        bucket_name,
        prefix=prefix,
        recursive=recursive,
    )
    return [obj.object_name for obj in objects if obj.object_name is not None]
