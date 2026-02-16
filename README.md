# Production Control — Система контроля заданий на выпуск продукции

Веб-приложение для управления сменными заданиями на производстве с асинхронной обработкой задач, файловым хранилищем и внешними интеграциями.

## 1. Обзор системы

### Назначение

Система предназначена для автоматизации управления производственным процессом:
- создание и отслеживание сменных заданий (партий)
- учёт произведённой продукции с уникальными кодами маркировки
- массовая агрегация продукции (упаковка в короба/паллеты)
- генерация отчётов (Excel, CSV, PDF)
- webhook-уведомления о событиях в системе

### Пользователи

| Роль               | Задачи                                                  |
|--------------------|---------------------------------------------------------|
| Оператор линии     | Регистрация продукции, смена статусов, агрегация        |
| Руководитель смены | Создание партий, контроль выполнения, аналитика         |
| Аналитик           | Отчёты за период, производственная статистика           |
| Внешняя система    | Получение событий через webhooks, импорт/экспорт данных |

### Архитектура

```mermaid
graph TB
    Client[Клиент / UI] -->|HTTP REST| API[FastAPI API :8000]
    API -->|async| PG[(PostgreSQL 16)]
    API -->|cache| Redis[(Redis 7)]
    API -->|publish task| RMQ[(RabbitMQ 3.13)]
    RMQ -->|consume| Worker[Celery Worker]
    Worker -->|read/write| PG
    Worker -->|upload/download| MinIO[(MinIO S3)]
    Worker -->|send webhook| ExtSys[Внешняя система]
    Beat[Celery Beat] -->|schedule| RMQ
    Flower[Flower :5555] -->|monitor| Worker

    style API fill:#2d9cdb,color:#fff
    style Worker fill:#27ae60,color:#fff
    style Beat fill:#f39c12,color:#fff
```

### Технологический стек

| Компонент         | Технология            | Версия |
|-------------------|-----------------------|--------|
| API               | FastAPI + Uvicorn     | 0.100+ |
| ORM               | SQLAlchemy (async)    | 2.0+   |
| Валидация         | Pydantic              | v2     |
| БД                | PostgreSQL            | 16     |
| Миграции          | Alembic               | 1.13+  |
| Task Queue        | Celery                | 5.3+   |
| Message Broker    | RabbitMQ              | 3.13   |
| Cache             | Redis                 | 7+     |
| File Storage      | MinIO (S3-compatible) | latest |
| Логирование       | Loguru                | 0.7+   |
| Пакетный менеджер | Poetry                | 1.7+   |

---

## 2. Описание компонентов

### 2.1 API (FastAPI)

Пять групп эндпоинтов, все под префиксом `/api/v1`:

#### Batches — Партии (сменные задания)

| Метод    | Путь            | Описание                                                          |
|----------|-----------------|-------------------------------------------------------------------|
| `POST`   | `/batches/`     | Создать партию                                                    |
| `GET`    | `/batches/`     | Список партий (фильтр: status, work_center_id, date_from/date_to) |
| `GET`    | `/batches/{id}` | Получить партию по ID                                             |
| `PATCH`  | `/batches/{id}` | Обновить партию / сменить статус                                  |
| `DELETE` | `/batches/{id}` | Удалить партию                                                    |

Жизненный цикл статусов партии:

```
planned ──→ in_progress ──→ completed
   │              │
   └──→ cancelled ←──┘
```

#### Products — Продукция

| Метод    | Путь                    | Описание                                                  |
|----------|-------------------------|-----------------------------------------------------------|
| `POST`   | `/products/`            | Создать единицу продукции                                 |
| `GET`    | `/products/`            | Список продукции (фильтр: batch_id, status, product_type) |
| `GET`    | `/products/{id}`        | Получить продукцию по ID                                  |
| `PATCH`  | `/products/{id}`        | Обновить продукцию / сменить статус                       |
| `DELETE` | `/products/{id}`        | Удалить продукцию                                         |
| `POST`   | `/products/bulk-status` | Массовое обновление статуса (до 1000 кодов)               |

Жизненный цикл статусов продукции:

```
produced ──→ aggregated ──→ shipped
   │
   └──→ rejected
```

#### Webhooks — Подписки на события

| Метод    | Путь                        | Описание                                        |
|----------|-----------------------------|-------------------------------------------------|
| `POST`   | `/webhooks/`                | Создать подписку                                |
| `GET`    | `/webhooks/`                | Список подписок (фильтр: event_type, is_active) |
| `GET`    | `/webhooks/{id}`            | Получить подписку по ID                         |
| `PATCH`  | `/webhooks/{id}`            | Обновить подписку                               |
| `DELETE` | `/webhooks/{id}`            | Удалить подписку                                |
| `GET`    | `/webhooks/{id}/deliveries` | История доставок                                |

Доступные события: `batch.created`, `batch.started`, `batch.completed`, `batch.cancelled`, `product.aggregated`.

#### Tasks — Фоновые задачи (Celery)

| Метод  | Путь                      | Описание                      |
|--------|---------------------------|-------------------------------|
| `GET`  | `/tasks/{task_id}`        | Статус задачи                 |
| `POST` | `/tasks/import`           | Запустить импорт из Excel/CSV |
| `POST` | `/tasks/export`           | Запустить экспорт в Excel/CSV |
| `POST` | `/tasks/aggregation`      | Запустить массовую агрегацию  |
| `POST` | `/tasks/{task_id}/revoke` | Отменить задачу               |

#### Analytics — Аналитика

| Метод | Путь                           | Описание                                          |
|-------|--------------------------------|---------------------------------------------------|
| `GET` | `/analytics/batches/summary`   | Сводка: количество партий по статусам             |
| `GET` | `/analytics/batches/{id}`      | Детальная аналитика партии (план/факт, продукция) |
| `GET` | `/analytics/production-report` | Отчёт за период (date_from, date_to)              |

#### Health Check

| Метод | Путь      | Описание                                        |
|-------|-----------|-------------------------------------------------|
| `GET` | `/health` | Проверка работоспособности → `{"status": "ok"}` |

### 2.2 Background Tasks (Celery)

6 модулей задач, распределённых по 3 очередям:

| Задача                    | Очередь   | Описание                                     |
|---------------------------|-----------|----------------------------------------------|
| `aggregate_products_task` | `default` | Массовая агрегация продукции (chunks по 500) |
| `send_webhook_task`       | `default` | Отправка webhook с HMAC-подписью и retry     |
| `generate_report_task`    | `reports` | Генерация Excel/PDF отчётов → MinIO          |
| `generate_daily_report`   | `reports` | Ежедневный отчёт (Celery Beat, 06:00 UTC)    |
| `import_products_task`    | `imports` | Импорт продукции из Excel/CSV файла          |
| `export_data_task`        | `imports` | Экспорт данных в Excel/CSV → MinIO           |

Периодические задачи (Celery Beat):
- `cleanup_expired_results` — очистка результатов, каждый час
- `generate_daily_report` — дневной отчёт, ежедневно в 06:00 UTC
- `check_stale_batches` — проверка зависших партий, каждые 30 минут

### 2.3 Database Schema

5 таблиц в PostgreSQL:

```mermaid
erDiagram
    work_centers ||--o{ batches : "has many"
    batches ||--o{ products : "has many"
    webhook_subscriptions ||--o{ webhook_deliveries : "has many"

    work_centers {
        int id PK
        string code UK
        string name
        bool is_active
        datetime created_at
        datetime updated_at
    }

    batches {
        int id PK
        string number UK
        int work_center_id FK
        datetime shift_date
        int shift_number
        string status
        decimal planned_quantity
        decimal actual_quantity
        datetime started_at
        datetime completed_at
        datetime created_at
        datetime updated_at
    }

    products {
        int id PK
        string code UK
        int batch_id FK
        string status
        string product_type
        text extra_data
        datetime produced_at
        datetime created_at
        datetime updated_at
    }

    webhook_subscriptions {
        int id PK
        string name
        string target_url
        string event_type
        string secret
        bool is_active
        datetime created_at
        datetime updated_at
    }

    webhook_deliveries {
        int id PK
        int subscription_id FK
        string status
        text request_body
        int response_status
        text response_body
        string error_message
        int attempt_number
        int duration_ms
        datetime attempted_at
    }
```

### 2.4 File Storage (MinIO)

S3-совместимое хранилище с двумя бакетами:

| Бакет     | Назначение                                 |
|-----------|--------------------------------------------|
| `reports` | Сгенерированные отчёты (Excel, PDF)        |
| `imports` | Загруженные файлы для импорта (Excel, CSV) |

Операции: upload, download, delete, presigned URL (временная ссылка на скачивание).

### 2.5 Cache (Redis)

- Кэширование аналитических запросов (декоратор `@cached`)
- Операции: get, set (с TTL), delete, delete by pattern
- Хранение результатов Celery-задач (backend)
- Политика вытеснения: `allkeys-lru`, лимит 128 MB

### 2.6 Webhooks

- Подписка на события через REST API
- Тело запроса подписывается HMAC-SHA256 (заголовок `X-Webhook-Signature`)
- Автоматические retry при ошибках (Celery)
- История доставок с HTTP-статусом, телом ответа и длительностью

### 2.7 Конфигурация (Environment Variables)

| Переменная              | Описание                           | По умолчанию                          |
|-------------------------|------------------------------------|---------------------------------------|
| `APP_NAME`              | Название приложения                | `production-control`                  |
| `APP_ENV`               | Окружение (development/production) | `development`                         |
| `DEBUG`                 | Режим отладки                      | `true`                                |
| `SECRET_KEY`            | Секретный ключ приложения          | —                                     |
| `DB_HOST`               | Хост PostgreSQL                    | `localhost`                           |
| `DB_PORT`               | Порт PostgreSQL                    | `5432`                                |
| `DB_USER`               | Пользователь БД                    | `product_user`                        |
| `DB_PASSWORD`           | Пароль БД                          | `product_password`                    |
| `DB_NAME`               | Имя базы данных                    | `product_control`                     |
| `REDIS_HOST`            | Хост Redis                         | `localhost`                           |
| `REDIS_PORT`            | Порт Redis                         | `6379`                                |
| `REDIS_DB`              | Номер базы Redis                   | `0`                                   |
| `RABBITMQ_HOST`         | Хост RabbitMQ                      | `localhost`                           |
| `RABBITMQ_PORT`         | Порт RabbitMQ                      | `5672`                                |
| `RABBITMQ_USER`         | Пользователь RabbitMQ              | `guest`                               |
| `RABBITMQ_PASSWORD`     | Пароль RabbitMQ                    | `guest`                               |
| `MINIO_HOST`            | Хост MinIO                         | `localhost`                           |
| `MINIO_PORT`            | Порт MinIO S3 API                  | `9000`                                |
| `MINIO_ACCESS_KEY`      | Access key MinIO                   | `minioadmin`                          |
| `MINIO_SECRET_KEY`      | Secret key MinIO                   | `minioadmin`                          |
| `CELERY_BROKER_URL`     | URL брокера Celery                 | `amqp://guest:guest@localhost:5672//` |
| `CELERY_RESULT_BACKEND` | URL бэкенда результатов            | `redis://localhost:6379/0`            |

---

## 3. Data Flow диаграммы

### 3.1 Создание партии и учёт продукции

```mermaid
sequenceDiagram
    participant C as Клиент
    participant API as FastAPI
    participant DB as PostgreSQL
    participant WH as Webhook Service

    C->>API: POST /api/v1/batches/ (number, work_center_id, ...)
    API->>DB: INSERT INTO batches (status=planned)
    DB-->>API: Batch created
    API->>WH: trigger_event(batch.created, payload)
    WH->>DB: INSERT INTO webhook_deliveries
    API-->>C: 201 Created {batch}

    Note over C,DB: Оператор регистрирует продукцию

    C->>API: POST /api/v1/products/ (code, batch_id, product_type)
    API->>DB: INSERT INTO products (status=produced)
    DB-->>API: Product created
    API-->>C: 201 Created {product}

    C->>API: PATCH /api/v1/batches/{id} (status=in_progress)
    API->>DB: UPDATE batches SET status=in_progress, started_at=now()
    API->>WH: trigger_event(batch.started, payload)
    API-->>C: 200 OK {batch}

    C->>API: PATCH /api/v1/batches/{id} (status=completed)
    API->>DB: UPDATE batches SET status=completed, completed_at=now()
    API->>WH: trigger_event(batch.completed, payload)
    API-->>C: 200 OK {batch}
```

### 3.2 Массовая агрегация

```mermaid
sequenceDiagram
    participant C as Клиент
    participant API as FastAPI
    participant RMQ as RabbitMQ
    participant W as Celery Worker
    participant DB as PostgreSQL
    participant WH as Webhook Task

    C->>API: POST /api/v1/tasks/aggregation {batch_id, codes[]}
    API->>RMQ: aggregate_products_task.delay()
    API-->>C: 202 Accepted {task_id}

    RMQ->>W: consume task
    loop Chunks по 500 кодов
        W->>DB: UPDATE products SET status=aggregated WHERE code IN (chunk)
    end
    W->>RMQ: send_webhook_task.delay(product.aggregated)
    W-->>RMQ: task SUCCESS

    RMQ->>WH: consume webhook task
    WH->>WH: HMAC-SHA256 подпись
    WH->>WH: POST target_url (payload + X-Webhook-Signature)

    C->>API: GET /api/v1/tasks/{task_id}
    API-->>C: 200 OK {status: SUCCESS, result: {updated: N}}
```

### 3.3 Генерация отчёта и экспорт

```mermaid
sequenceDiagram
    participant C as Клиент
    participant API as FastAPI
    participant RMQ as RabbitMQ
    participant W as Celery Worker
    participant DB as PostgreSQL
    participant S3 as MinIO

    C->>API: POST /api/v1/tasks/export {format: xlsx, date_from, date_to}
    API->>RMQ: export_data_task.delay()
    API-->>C: 202 Accepted {task_id}

    RMQ->>W: consume task
    W->>DB: SELECT batches + products за период
    W->>W: Генерация Excel (openpyxl)
    W->>S3: upload(reports/export_2026-02-16.xlsx)
    S3-->>W: OK
    W->>S3: presigned_url(file, expires=1h)
    S3-->>W: https://minio:9000/reports/export_...?signature=...
    W-->>RMQ: task SUCCESS {download_url}

    C->>API: GET /api/v1/tasks/{task_id}
    API-->>C: 200 OK {status: SUCCESS, result: {download_url: "..."}}
```

---

## 4. Инфраструктура

### Docker Compose

8 контейнеров:

| Сервис          | Образ                           | Порт        | Назначение                      |
|-----------------|---------------------------------|-------------|---------------------------------|
| `postgres`      | postgres:16-alpine              | 5432        | База данных                     |
| `redis`         | redis:7-alpine                  | 6379        | Кэш + Celery backend            |
| `rabbitmq`      | rabbitmq:3.13-management-alpine | 5672, 15672 | Message broker + Management UI  |
| `minio`         | minio/minio                     | 9000, 9001  | S3 хранилище + Console          |
| `api`           | Dockerfile (multi-stage)        | 8000        | FastAPI приложение              |
| `celery-worker` | Dockerfile                      | —           | Обработка фоновых задач         |
| `celery-beat`   | Dockerfile                      | —           | Планировщик периодических задач |
| `flower`        | Dockerfile                      | 5555        | Мониторинг Celery               |

### Запуск

```bash
# 1. Скопировать переменные окружения
cp .env.example .env

# 2. Запустить все сервисы
docker compose up -d

# 3. Применить миграции БД
docker compose exec api alembic upgrade head

# 4. Инициализировать бакеты MinIO
docker compose exec api python -m scripts.init_minio

# 5. Проверить работоспособность
curl http://localhost:8000/health
# → {"status": "ok"}
```

### Остановка

```bash
docker compose down          # остановить контейнеры
docker compose down -v       # + удалить volumes (данные)
```

### Мониторинг

| Сервис              | URL                         | Назначение                                 |
|---------------------|-----------------------------|--------------------------------------------|
| Swagger UI          | http://localhost:8000/docs  | Интерактивная документация API             |
| ReDoc               | http://localhost:8000/redoc | Альтернативная документация API            |
| Flower              | http://localhost:5555       | Мониторинг Celery workers и задач          |
| RabbitMQ Management | http://localhost:15672      | Управление очередями (guest/guest)         |
| MinIO Console       | http://localhost:9001       | Управление файлами (minioadmin/minioadmin) |

### Healthchecks

Все инфраструктурные сервисы имеют healthcheck-проверки в Docker Compose:

| Сервис     | Проверка                    | Интервал |
|------------|-----------------------------|----------|
| PostgreSQL | `pg_isready`                | 5s       |
| Redis      | `redis-cli ping`            | 5s       |
| RabbitMQ   | `rabbitmq-diagnostics ping` | 10s      |
| MinIO      | `curl /minio/health/live`   | 10s      |

Сервисы приложения (`api`, `celery-worker`, `celery-beat`, `flower`) запускаются только после того, как все инфраструктурные сервисы прошли healthcheck.

---

## 5. Development Guide

### Локальная разработка

```bash
# Создать виртуальное окружение
python3.11 -m venv venv
source venv/bin/activate

# Установить зависимости через Poetry
pip install poetry
poetry install

# Скопировать переменные окружения
cp .env.example .env
# Отредактировать .env при необходимости
```

### Запуск тестов

```bash
# Все тесты (185 тестов: 85 unit + 67 integration + conftest)
pytest tests/ -v

# Без измерения покрытия (быстрее)
pytest tests/ -v --no-cov

# Только unit-тесты
pytest tests/unit/ -v

# Только integration-тесты
pytest tests/integration/ -v
```

Тесты используют SQLite in-memory (aiosqlite) — внешние сервисы не нужны.

### Структура проекта

```
production-control/
├── alembic/                    # Миграции БД
│   ├── versions/               # Файлы миграций
│   ├── env.py                  # Настройка Alembic
│   └── script.py.mako          # Шаблон миграций
├── scripts/
│   └── init_minio.py           # Инициализация бакетов MinIO
├── src/
│   ├── api/v1/
│   │   ├── routers/            # Эндпоинты API
│   │   │   ├── analytics.py    #   Аналитика
│   │   │   ├── batches.py      #   CRUD партий
│   │   │   ├── products.py     #   CRUD продукции
│   │   │   ├── tasks.py        #   Управление Celery-задачами
│   │   │   └── webhooks.py     #   Управление подписками
│   │   └── schemas/            # Pydantic-схемы (request/response)
│   │       ├── batch.py
│   │       ├── common.py
│   │       ├── product.py
│   │       ├── task.py
│   │       └── webhook.py
│   ├── core/
│   │   ├── cache.py            # Redis клиент + @cached декоратор
│   │   ├── config.py           # Pydantic Settings (все env vars)
│   │   ├── database.py         # Async SQLAlchemy (engine, session)
│   │   ├── dependencies.py     # FastAPI Depends
│   │   └── exceptions.py       # Базовые исключения (AppError, AppException)
│   ├── data/
│   │   ├── models/             # SQLAlchemy модели
│   │   │   ├── batch.py        #   Партия + BatchStatus
│   │   │   ├── product.py      #   Продукция + ProductStatus
│   │   │   ├── webhook.py      #   WebhookSubscription + WebhookDelivery
│   │   │   └── work_center.py  #   Рабочий центр
│   │   └── repositories/       # Data Access Layer
│   │       ├── base_repository.py
│   │       ├── batch_repository.py
│   │       ├── product_repository.py
│   │       └── webhook_repository.py
│   ├── domain/
│   │   ├── exceptions/         # Доменные исключения
│   │   └── services/           # Бизнес-логика
│   │       ├── analytics_service.py
│   │       ├── batch_service.py
│   │       ├── product_service.py
│   │       └── webhook_service.py
│   ├── storage/
│   │   └── minio_service.py    # MinIO S3 клиент
│   ├── tasks/                  # Celery задачи
│   │   ├── aggregation.py      #   Массовая агрегация
│   │   ├── exports.py          #   Экспорт данных
│   │   ├── imports.py          #   Импорт из Excel/CSV
│   │   ├── reports.py          #   Генерация отчётов
│   │   ├── scheduled.py        #   Периодические задачи (Beat)
│   │   └── webhooks.py         #   Отправка webhooks
│   ├── utils/                  # Утилиты
│   │   ├── excel_generator.py  #   Генерация Excel
│   │   ├── excel_parser.py     #   Парсинг Excel/CSV
│   │   ├── hmac_utils.py       #   HMAC-SHA256 подписи
│   │   └── pdf_generator.py    #   Генерация PDF
│   ├── celery_app.py           # Конфигурация Celery
│   └── main.py                 # Точка входа FastAPI
├── tests/
│   ├── conftest.py             # Fixtures (async SQLite, фабрики)
│   ├── unit/                   # Unit-тесты (85)
│   └── integration/            # Integration-тесты (67)
├── .env.example                # Пример переменных окружения
├── .pre-commit-config.yaml     # Pre-commit хуки
├── alembic.ini                 # Конфигурация Alembic
├── docker-compose.yml          # Docker Compose (8 сервисов)
├── Dockerfile                  # Multi-stage build
├── pyproject.toml              # Poetry + конфигурация инструментов
└── poetry.lock                 # Lock-файл зависимостей
```

### Code Quality

```bash
# Линтер (ruff)
ruff check src/ tests/

# Форматирование (black)
black src/ tests/

# Статическая типизация (mypy)
mypy src/

# Анализ безопасности (bandit)
bandit -r src/ -c pyproject.toml

# Все проверки разом (pre-commit)
pre-commit run --all-files
```

### API документация

После запуска приложения доступна автогенерируемая документация:

- **Swagger UI**: http://localhost:8000/docs — интерактивное тестирование эндпоинтов
- **ReDoc**: http://localhost:8000/redoc — читаемая документация

### Git Workflow

```bash
# Основная ветка
main

# Ветка разработки
feature/production-control

# Коммиты
git commit -m "dev: описание новой функциональности"
git commit -m "fix: описание исправления"

# Финальный Pull Request
feature/production-control → main
```
