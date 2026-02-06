from ...core.exceptions import ConflictError, NotFoundError, ValidationError

# === Исключения для партий (Batch) ===


class BatchNotFoundError(NotFoundError):
    """Партия не найдена."""

    message = "Партия не найдена"


class BatchAlreadyExistsError(ConflictError):
    """Партия с таким номером уже существует."""

    message = "Партия с таким номером уже существует"


class InvalidBatchStatusError(ValidationError):
    """Недопустимый переход статуса партии."""

    message = "Недопустимый переход статуса партии"


# === Исключения для продукции (Product) ===


class ProductNotFoundError(NotFoundError):
    """Единица продукции не найдена."""

    message = "Единица продукции не найдена"


class ProductAlreadyExistsError(ConflictError):
    """Продукция с таким кодом уже существует."""

    message = "Продукция с таким кодом уже существует"


class InvalidProductStatusError(ValidationError):
    """Недопустимый переход статуса продукции."""

    message = "Недопустимый переход статуса продукции"


# === Исключения для webhooks ===


class WebhookNotFoundError(NotFoundError):
    """Webhook-подписка не найдена."""

    message = "Webhook-подписка не найдена"


class WebhookDeliveryError(ValidationError):
    """Ошибка доставки webhook."""

    message = "Ошибка доставки webhook"


__all__ = [
    "BatchNotFoundError",
    "BatchAlreadyExistsError",
    "InvalidBatchStatusError",
    "ProductNotFoundError",
    "ProductAlreadyExistsError",
    "InvalidProductStatusError",
    "WebhookNotFoundError",
    "WebhookDeliveryError",
]
