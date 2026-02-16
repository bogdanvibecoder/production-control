"""Утилита HMAC-SHA256 подписей для webhook-уведомлений."""

from __future__ import annotations

import hashlib
import hmac
import secrets

# Алгоритм хеширования
HASH_ALGORITHM = hashlib.sha256

# Префикс подписи в заголовке X-Webhook-Signature
SIGNATURE_PREFIX = "sha256="

# Длина генерируемого секрета (байт)
SECRET_LENGTH = 32


def sign(secret: str, payload: str) -> str:
    """Создать HMAC-SHA256 подпись payload'а.

    Args:
        secret: Секретный ключ подписки (``WebhookSubscription.secret``).
        payload: Тело запроса (JSON-строка ``WebhookDelivery.request_body``).

    Returns:
        Hex-дайджест подписи **без** префикса ``sha256=``.
        Для формирования заголовка используйте: ``f"sha256={sign(...)}"``
    """
    digest: str = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        HASH_ALGORITHM,
    ).hexdigest()
    return digest


def verify(secret: str, payload: str, signature: str) -> bool:
    """Проверить HMAC-SHA256 подпись.

    Принимает подпись как с префиксом ``sha256=...``, так и без него.
    Использует ``hmac.compare_digest`` для защиты от timing-атак.

    Args:
        secret: Секретный ключ подписки.
        payload: Тело запроса.
        signature: Подпись для проверки (значение заголовка
            ``X-Webhook-Signature``).

    Returns:
        ``True`` если подпись валидна, ``False`` иначе.
    """
    if signature.startswith(SIGNATURE_PREFIX):
        signature = signature[len(SIGNATURE_PREFIX) :]

    expected = sign(secret, payload)
    return hmac.compare_digest(expected, signature)


def generate_secret() -> str:
    """Сгенерировать криптографически стойкий секретный ключ.

    Используется при создании новой ``WebhookSubscription``,
    если пользователь не предоставил свой секрет.

    Returns:
        Hex-строка длиной 64 символа (32 байта энтропии).
    """
    return secrets.token_hex(SECRET_LENGTH)
