"""Integration-тесты для health check (/health)."""

from httpx import AsyncClient


class TestHealthCheck:
    """Тесты health check endpoint."""

    async def test_health_200(self, client: AsyncClient) -> None:
        """Health check → 200 + {"status": "ok"}."""
        response = await client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
