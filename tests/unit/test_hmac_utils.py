"""Unit-тесты для утилит HMAC-подписей."""

from src.utils.hmac_utils import generate_secret, sign, verify

# ============================================================================
# Создание подписи
# ============================================================================


class TestSign:
    """Тесты функции sign()."""

    def test_sign_returns_hex_string(self) -> None:
        """Подпись — hex-строка (только символы 0-9a-f)."""
        result = sign("secret", "payload")

        assert isinstance(result, str)
        assert all(c in "0123456789abcdef" for c in result)

    def test_sign_deterministic(self) -> None:
        """Одинаковые входные данные дают одинаковую подпись."""
        sig1 = sign("my-secret", "my-payload")
        sig2 = sign("my-secret", "my-payload")

        assert sig1 == sig2

    def test_sign_different_secrets(self) -> None:
        """Разные секреты дают разные подписи."""
        sig1 = sign("secret-1", "payload")
        sig2 = sign("secret-2", "payload")

        assert sig1 != sig2

    def test_sign_different_payloads(self) -> None:
        """Разные payload дают разные подписи."""
        sig1 = sign("secret", "payload-1")
        sig2 = sign("secret", "payload-2")

        assert sig1 != sig2

    def test_sign_sha256_length(self) -> None:
        """SHA-256 дайджест — 64 символа (32 байта в hex)."""
        result = sign("secret", "payload")

        assert len(result) == 64


# ============================================================================
# Проверка подписи
# ============================================================================


class TestVerify:
    """Тесты функции verify()."""

    def test_verify_valid_signature(self) -> None:
        """Валидная подпись проходит проверку."""
        secret = "my-secret"
        payload = '{"event": "batch.completed"}'
        signature = sign(secret, payload)

        assert verify(secret, payload, signature) is True

    def test_verify_with_prefix(self) -> None:
        """Подпись с префиксом sha256= проходит проверку."""
        secret = "my-secret"
        payload = "test-payload"
        signature = sign(secret, payload)

        assert verify(secret, payload, f"sha256={signature}") is True

    def test_verify_invalid_signature(self) -> None:
        """Невалидная подпись не проходит проверку."""
        assert verify("secret", "payload", "invalid-hex-string") is False

    def test_verify_wrong_secret(self) -> None:
        """Подпись от другого секрета не проходит проверку."""
        payload = "test"
        signature = sign("correct-secret", payload)

        assert verify("wrong-secret", payload, signature) is False

    def test_verify_tampered_payload(self) -> None:
        """Изменённый payload не проходит проверку."""
        secret = "my-secret"
        signature = sign(secret, "original")

        assert verify(secret, "tampered", signature) is False


# ============================================================================
# Генерация секрета
# ============================================================================


class TestGenerateSecret:
    """Тесты функции generate_secret()."""

    def test_generate_returns_hex(self) -> None:
        """Секрет — hex-строка."""
        secret = generate_secret()

        assert isinstance(secret, str)
        assert all(c in "0123456789abcdef" for c in secret)

    def test_generate_length(self) -> None:
        """Секрет — 64 символа (32 байта энтропии в hex)."""
        secret = generate_secret()

        assert len(secret) == 64

    def test_generate_unique(self) -> None:
        """Каждый вызов генерирует уникальный секрет."""
        secrets = {generate_secret() for _ in range(10)}

        assert len(secrets) == 10
