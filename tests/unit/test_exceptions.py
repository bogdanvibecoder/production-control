"""Unit-тесты для иерархии исключений."""

from http import HTTPStatus

from src.core.exceptions import (
    AppError,
    AppException,
    ConflictError,
    ForbiddenError,
    InternalError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from src.domain.exceptions import (
    BatchAlreadyExistsError,
    BatchNotFoundError,
    InvalidBatchStatusError,
    InvalidProductStatusError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
    WebhookDeliveryError,
    WebhookNotFoundError,
)

# ============================================================================
# Базовые исключения (core)
# ============================================================================


class TestAppError:
    """Тесты базового исключения AppError."""

    def test_default_message(self) -> None:
        """Сообщение по умолчанию."""
        err = AppError()

        assert err.message == "Внутренняя ошибка сервера"
        assert err.status_code == HTTPStatus.INTERNAL_SERVER_ERROR

    def test_custom_message(self) -> None:
        """Кастомное сообщение перезаписывает дефолт."""
        err = AppError(message="Что-то пошло не так")

        assert err.message == "Что-то пошло не так"

    def test_details(self) -> None:
        """Детали передаются и сохраняются."""
        err = AppError(details={"field": "value"})

        assert err.details == {"field": "value"}

    def test_to_dict_without_details(self) -> None:
        """to_dict() без деталей — только error и message."""
        err = AppError()
        result = err.to_dict()

        assert result["error"] == "AppError"
        assert result["message"] == "Внутренняя ошибка сервера"
        assert "details" not in result

    def test_to_dict_with_details(self) -> None:
        """to_dict() с деталями — включает поле details."""
        err = AppError(details={"id": 42})
        result = err.to_dict()

        assert result["details"] == {"id": 42}

    def test_str_representation(self) -> None:
        """str() возвращает сообщение."""
        err = AppError(message="Тест")

        assert str(err) == "Тест"


class TestAppException:
    """Тесты универсального исключения AppException."""

    def test_custom_status_code(self) -> None:
        """Кастомный HTTP-код устанавливается."""
        err = AppException(
            status_code=418,
            message="I'm a teapot",
        )

        assert err.status_code == 418
        assert err.message == "I'm a teapot"

    def test_with_details(self) -> None:
        """AppException с деталями."""
        err = AppException(
            status_code=400,
            message="Ошибка",
            details={"reason": "bad input"},
        )

        result = err.to_dict()
        assert result["error"] == "AppException"
        assert result["details"] == {"reason": "bad input"}

    def test_inherits_app_error(self) -> None:
        """AppException наследует от AppError."""
        err = AppException(status_code=400, message="test")

        assert isinstance(err, AppError)


# ============================================================================
# HTTP-исключения с фиксированными кодами
# ============================================================================


class TestHttpExceptions:
    """Тесты исключений с фиксированными HTTP-кодами."""

    def test_not_found_error(self) -> None:
        """NotFoundError → 404."""
        err = NotFoundError()

        assert err.status_code == HTTPStatus.NOT_FOUND
        assert err.message == "Ресурс не найден"

    def test_conflict_error(self) -> None:
        """ConflictError → 409."""
        err = ConflictError()

        assert err.status_code == HTTPStatus.CONFLICT
        assert err.message == "Конфликт данных"

    def test_validation_error(self) -> None:
        """ValidationError → 422."""
        err = ValidationError()

        assert err.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert err.message == "Ошибка валидации данных"

    def test_forbidden_error(self) -> None:
        """ForbiddenError → 403."""
        err = ForbiddenError()

        assert err.status_code == HTTPStatus.FORBIDDEN
        assert err.message == "Доступ запрещён"

    def test_unauthorized_error(self) -> None:
        """UnauthorizedError → 401."""
        err = UnauthorizedError()

        assert err.status_code == HTTPStatus.UNAUTHORIZED
        assert err.message == "Требуется аутентификация"

    def test_internal_error(self) -> None:
        """InternalError → 500."""
        err = InternalError()

        assert err.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert err.message == "Внутренняя ошибка сервера"

    def test_all_inherit_app_error(self) -> None:
        """Все HTTP-исключения наследуют от AppError."""
        exceptions = [
            NotFoundError(),
            ConflictError(),
            ValidationError(),
            ForbiddenError(),
            UnauthorizedError(),
            InternalError(),
        ]

        for exc in exceptions:
            assert isinstance(exc, AppError)


# ============================================================================
# Доменные исключения
# ============================================================================


class TestDomainExceptions:
    """Тесты доменных исключений — наследование и сообщения."""

    # --- Batch ---

    def test_batch_not_found(self) -> None:
        """BatchNotFoundError наследует NotFoundError (404)."""
        err = BatchNotFoundError(details={"batch_id": 1})

        assert isinstance(err, NotFoundError)
        assert err.status_code == HTTPStatus.NOT_FOUND
        assert err.message == "Партия не найдена"
        assert err.details == {"batch_id": 1}

    def test_batch_already_exists(self) -> None:
        """BatchAlreadyExistsError наследует ConflictError (409)."""
        err = BatchAlreadyExistsError()

        assert isinstance(err, ConflictError)
        assert err.status_code == HTTPStatus.CONFLICT
        assert err.message == "Партия с таким номером уже существует"

    def test_invalid_batch_status(self) -> None:
        """InvalidBatchStatusError наследует ValidationError (422)."""
        err = InvalidBatchStatusError()

        assert isinstance(err, ValidationError)
        assert err.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert err.message == "Недопустимый переход статуса партии"

    # --- Product ---

    def test_product_not_found(self) -> None:
        """ProductNotFoundError наследует NotFoundError (404)."""
        err = ProductNotFoundError()

        assert isinstance(err, NotFoundError)
        assert err.message == "Единица продукции не найдена"

    def test_product_already_exists(self) -> None:
        """ProductAlreadyExistsError наследует ConflictError (409)."""
        err = ProductAlreadyExistsError()

        assert isinstance(err, ConflictError)
        assert err.message == "Продукция с таким кодом уже существует"

    def test_invalid_product_status(self) -> None:
        """InvalidProductStatusError наследует ValidationError (422)."""
        err = InvalidProductStatusError()

        assert isinstance(err, ValidationError)
        assert err.message == "Недопустимый переход статуса продукции"

    # --- Webhook ---

    def test_webhook_not_found(self) -> None:
        """WebhookNotFoundError наследует NotFoundError (404)."""
        err = WebhookNotFoundError()

        assert isinstance(err, NotFoundError)
        assert err.message == "Webhook-подписка не найдена"

    def test_webhook_delivery_error(self) -> None:
        """WebhookDeliveryError наследует ValidationError (422)."""
        err = WebhookDeliveryError()

        assert isinstance(err, ValidationError)
        assert err.message == "Ошибка доставки webhook"

    def test_domain_to_dict(self) -> None:
        """to_dict() доменного исключения содержит правильное имя класса."""
        err = BatchNotFoundError(details={"batch_id": 5})
        result = err.to_dict()

        assert result["error"] == "BatchNotFoundError"
        assert result["message"] == "Партия не найдена"
        assert result["details"] == {"batch_id": 5}
