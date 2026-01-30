from typing import Any
from http import HTTPStatus

class AppError(Exception):
    """ Базовое исключение приложения """

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    message: str = "Внутренняя ошибка сервера"

    def __init__(
            self,
            message: str | None = None,
            details: Any = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.details = details
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """ Преобразование в словарь для JSON-ответа """
        result = {
            "error": self.__class__.__name__,
            "message": self.message,
        }
        if self.details is not None:
            result["details"] = self.details
        return result


class NotFoundError(AppError):
    """ Ресурс не найден """

    status_code: int = HTTPStatus.NOT_FOUND
    message: str = "Ресурс не найден"


class ConflictError(AppError):
    """ Конфликт данных (дубликат, нарушение уникальности) """

    status_code: int = HTTPStatus.CONFLICT
    message: str = "Конфликт данных"


class ValidationError(AppError):
    """ Ошибка валидации данных """

    status_code: int = HTTPStatus.UNPROCESSABLE_ENTITY
    message: str = "Ошибка валидации данных"


class ForbiddenError(AppError):
    """ Доступ запрещён """

    status_code: int = HTTPStatus.FORBIDDEN
    message: str = "Доступ запрещён"


class UnauthorizedError(AppError):
    """ Требуется аутентификация """

    status_code: int = HTTPStatus.UNAUTHORIZED
    message: str = "Требуется аутентификация"


class InternalError(AppError):
    """ Внутренняя ошибка сервера """

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    message: str = "Внутренняя ошибка сервера"


__all__ = [
    "AppError",
    "NotFoundError",
    "ConflictError",
    "ValidationError",
    "ForbiddenError",
    "UnauthorizedError",
    "InternalError",
]