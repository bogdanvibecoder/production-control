from fastapi import APIRouter, status

from ..schemas.task import (
    AggregationTaskRequest,
    ExportTaskRequest,
    ImportTaskRequest,
    TaskCreate,
    TaskResponse,
    TaskStatus,
)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Получить статус задачи",
    responses={
        200: {"description": "Статус задачи"},
    },
)
async def get_task_status(task_id: str) -> TaskResponse:
    """
    Получить статус Celery-задачи по ID.

    **Path-параметры:**
    - `task_id`: ID задачи (возвращается при постановке в очередь)

    **Возможные статусы:**
    - `PENDING` — задача ожидает выполнения
    - `STARTED` — задача выполняется
    - `SUCCESS` — задача завершена успешно
    - `FAILURE` — задача завершена с ошибкой
    - `RETRY` — задача будет повторена
    - `REVOKED` — задача отменена

    **Возвращает:** информацию о задаче: статус, результат, ошибки, прогресс.
    """
    from ....celery_app import celery_app  # type: ignore[attr-defined]

    result = celery_app.AsyncResult(task_id)

    response = TaskResponse(
        task_id=task_id,
        status=TaskStatus(result.status),
    )

    if result.status == "SUCCESS":
        response.result = result.result
    elif result.status == "FAILURE":
        response.error = str(result.result)

    # Прогресс (если задача передаёт meta)
    if result.status == "STARTED" and isinstance(result.info, dict):
        response.progress = result.info.get("progress")

    return response


@router.post(
    "/import",
    response_model=TaskCreate,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запустить импорт продукции",
    responses={
        202: {"description": "Задача поставлена в очередь"},
    },
)
async def launch_import(data: ImportTaskRequest) -> TaskCreate:
    """
    Запустить импорт продукции из файла (Excel/CSV).

    **Тело запроса:**
    - `batch_id`: ID партии, в которую импортируется продукция
    - `file_name`: имя файла в MinIO (предварительно загруженного)

    **Возвращает:** `task_id` для отслеживания прогресса.
    """
    from ....tasks.imports import import_products_task  # type: ignore[attr-defined]

    result = import_products_task.delay(
        batch_id=data.batch_id,
        file_name=data.file_name,
    )

    return TaskCreate(task_id=result.id)


@router.post(
    "/export",
    response_model=TaskCreate,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запустить экспорт данных",
    responses={
        202: {"description": "Задача поставлена в очередь"},
    },
)
async def launch_export(data: ExportTaskRequest) -> TaskCreate:
    """
    Запустить экспорт данных в файл (Excel/CSV).

    **Тело запроса:**
    - `export_format`: формат файла (xlsx или csv, по умолчанию xlsx)
    - `date_from`: начало диапазона дат (опционально)
    - `date_to`: конец диапазона дат (опционально)

    **Возвращает:** `task_id` для отслеживания прогресса.
    После завершения в `result` будет ссылка на файл в MinIO.
    """
    from ....tasks.exports import export_data_task  # type: ignore[attr-defined]

    result = export_data_task.delay(
        export_format=data.export_format,
        date_from=data.date_from.isoformat() if data.date_from else None,
        date_to=data.date_to.isoformat() if data.date_to else None,
    )

    return TaskCreate(task_id=result.id)


@router.post(
    "/aggregation",
    response_model=TaskCreate,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запустить массовую агрегацию",
    responses={
        202: {"description": "Задача поставлена в очередь"},
    },
)
async def launch_aggregation(data: AggregationTaskRequest) -> TaskCreate:
    """
    Запустить массовую агрегацию продукции.

    **Тело запроса:**
    - `batch_id`: ID партии
    - `codes`: список кодов продукции (от 1 до 10000)

    **Возвращает:** `task_id` для отслеживания прогресса.
    """
    from ....tasks.aggregation import aggregate_products_task  # type: ignore[attr-defined]

    result = aggregate_products_task.delay(
        batch_id=data.batch_id,
        codes=data.codes,
    )

    return TaskCreate(task_id=result.id)


@router.post(
    "/{task_id}/revoke",
    response_model=TaskResponse,
    summary="Отменить задачу",
    responses={
        200: {"description": "Задача отменена"},
    },
)
async def revoke_task(task_id: str) -> TaskResponse:
    """
    Отменить выполнение Celery-задачи.

    **Path-параметры:**
    - `task_id`: ID задачи

    **Примечание:** Если задача уже выполняется, она будет прервана
    (terminate=True). Если ещё в очереди — просто удалена.

    **Возвращает:** обновлённый статус задачи.
    """
    from ....celery_app import celery_app  # type: ignore[attr-defined]

    celery_app.control.revoke(task_id, terminate=True)

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.REVOKED,
    )
