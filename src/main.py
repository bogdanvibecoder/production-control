"""Точка входа FastAPI-приложения."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from .api.v1.routers.analytics import router as analytics_router
from .api.v1.routers.batches import router as batches_router
from .api.v1.routers.products import router as products_router
from .api.v1.routers.tasks import router as tasks_router
from .api.v1.routers.webhooks import router as webhooks_router
from .core.cache import redis_client
from .core.config import settings
from .core.database import engine
from .core.exceptions import AppError

# ---------------------------------------------------------------------------
# Loguru
# ---------------------------------------------------------------------------


def _setup_logging() -> None:
    """Настройка Loguru: убираем стандартный handler, добавляем свой."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
    )


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown логика приложения."""
    _setup_logging()
    logger.info("Приложение запускается — {}", settings.app_name)
    yield
    # Shutdown
    await redis_client.aclose()
    await engine.dispose()
    logger.info("Приложение остановлено")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """Преобразование AppError (и всех наследников) в JSON-ответ."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

API_PREFIX = "/api/v1"

app.include_router(batches_router, prefix=API_PREFIX)
app.include_router(products_router, prefix=API_PREFIX)
app.include_router(webhooks_router, prefix=API_PREFIX)
app.include_router(tasks_router, prefix=API_PREFIX)
app.include_router(analytics_router, prefix=API_PREFIX)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Проверка работоспособности приложения."""
    return {"status": "ok"}
