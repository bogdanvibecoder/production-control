from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Базовый путь проекта
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class DatabaseSettings(BaseSettings):
    """Настройки подключения к PostgreSQL"""

    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = Field(default="localhost")
    port: int = Field(default=5432)
    user: str = Field(default="postgres")
    password: str = Field(default="postgres")
    name: str = Field(default="production_control")
    echo: bool = Field(default=False)

    @computed_field  # type: ignore[misc]
    @property
    def async_dsn(self) -> str:
        """DNS для асинхронного подключения (asyncpg)"""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
        )

    @computed_field  # type: ignore[misc]
    @property
    def sync_dsn(self) -> str:
        """DNS для синхронного подключения (Alembic миграции)"""
        return (
            f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
        )


class RedisSettings(BaseSettings):
    """Настройки подключения к Redis"""

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str = Field(default="localhost")
    port: int = Field(default=6379)
    db: int = Field(default=0)
    password: str | None = Field(default=None)

    @computed_field  # type: ignore[misc]
    @property
    def url(self) -> str:
        """URL для подключения к Redis"""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class RabbitMQSettings(BaseSettings):
    """Настройка подключения к RabbitMQ"""

    model_config = SettingsConfigDict(env_prefix="RABBITMQ_")

    host: str = Field(default="localhost")
    port: int = Field(default=5672)
    user: str = Field(default="guest")
    password: str = Field(default="guest")
    vhost: str = Field(default="/")

    @computed_field  # type: ignore[misc]
    @property
    def url(self) -> str:
        """URL для подключения к RabbitMQ (AMQP"""
        return f"amqp://{self.user}:{self.password}@{self.host}:{self.port}/{self.vhost}"


class MinIOSettings(BaseSettings):
    """Настройки подключения к MinIO"""

    model_config = SettingsConfigDict(env_prefix="MINIO_")

    host: str = Field(default="localhost")
    port: int = Field(default=9000)
    access_key: str = Field(default="minioadmin")
    secret_key: str = Field(default="minioadmin")
    secure: bool = Field(default=False)
    bucket_reports: str = Field(default="reports")
    bucket_imports: str = Field(default="imports")

    @computed_field  # type: ignore[misc]
    @property
    def endpoint(self) -> str:
        """Endpoint для подключения к MinIO"""
        return f"{self.host}:{self.port}"


class CelerySettings(BaseSettings):
    """Настройки Celery"""

    model_config = SettingsConfigDict(env_prefix="CELERY_")

    task_default_queue: str = Field(default="default")
    task_acks_late: bool = Field(default=True)
    task_reject_on_worker_lost: bool = Field(default=True)
    worker_prefetch_multiplier: int = Field(default=1)
    result_expires: int = Field(default=3600)


class Settings(BaseSettings):
    """Главный класс настроек приложения"""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Основные настройки приложения
    app_name: str = Field(default="Production Control API")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO")

    # Вложенные настройки сервисов
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    minio: MinIOSettings = Field(default_factory=MinIOSettings)
    celery: CelerySettings = Field(default_factory=CelerySettings)


@lru_cache
def get_settings() -> Settings:
    """
    Возвращает закэшированный экземпляр настроек.
    Используется как зависимость FastAPI:
        settings: Settings = Depends(get_settings)
    """
    return Settings()


# Глобальный экземпляр для удобного импорта
settings = get_settings()
