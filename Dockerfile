# ============================================================================
# Stage 1: builder — установка зависимостей через Poetry
# ============================================================================
FROM python:3.11-slim AS builder

# Переменные Poetry: не создавать virtualenv, не спрашивать интерактивно
ENV POETRY_VERSION=1.8.5 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

# Устанавливаем Poetry
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

WORKDIR /build

# Копируем только файлы зависимостей (Docker кэширует этот слой)
COPY pyproject.toml poetry.lock ./

# Экспортируем зависимости в requirements.txt (без dev-зависимостей)
RUN poetry export --without dev --format requirements.txt --output requirements.txt

# ============================================================================
# Stage 2: runtime — финальный образ
# ============================================================================
FROM python:3.11-slim AS runtime

# Метаданные образа
LABEL maintainer="Bogdan <7777777@gmail.com>" \
      description="Production Control API" \
      version="0.1.0"

# Переменные окружения Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Системные зависимости для asyncpg и curl (healthcheck)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Устанавливаем Python-зависимости из requirements.txt (кэшируемый слой)
COPY --from=builder /build/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код и вспомогательные файлы
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/

# Порт FastAPI (Uvicorn)
EXPOSE 8000

# Healthcheck — проверяем /health каждые 30 секунд
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Запуск Uvicorn
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
