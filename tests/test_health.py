from __future__ import annotations

import httpx


class TestHealth:
    async def test_health_root(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["db"] == "connected"
        assert "tables" in data
        assert "rateLimit" in data

    async def test_health_api_prefix(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    async def test_health_redis_disconnected(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["redis"] == "disconnected"

    async def test_health_tables_list(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/health")
        data = resp.json()
        expected = ["users", "posts", "comments", "albums", "photos", "todos"]
        assert data["tables"] == expected

    async def test_health_rate_limit_config(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/health")
        data = resp.json()
        rl = data["rateLimit"]
        assert isinstance(rl["enabled"], bool)
        assert isinstance(rl["max"], int)
        assert isinstance(rl["windowMs"], int)


class TestInfo:
    async def test_info_root(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "Python JSON API Server" in data["message"]
        assert data["version"] == "1.0.0"
        assert "endpoints" in data

    async def test_info_api(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api")
        assert resp.status_code == 200
        data = resp.json()
        assert "endpoints" in data


class TestHealthDegraded:
    async def test_db_disconnected_marks_degraded(self) -> None:
        from fastapi import FastAPI

        from app.routes.health import router as health_router
        from app.services.runtime_config import RateLimitConfig

        app = FastAPI(title="health-only", lifespan=None)
        app.state.redis_client = None
        app.state.rate_limit_config = RateLimitConfig(
            enabled=True, max_requests=100, window_ms=60000
        )
        app.include_router(health_router)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["db"] == "disconnected"
        assert data["status"] == "degraded"

    async def test_db_probe_error_marks_degraded(self) -> None:
        from fastapi import FastAPI

        from app.routes.health import router as health_router
        from app.services.runtime_config import RateLimitConfig

        class FailingConnection:
            async def __aenter__(self) -> None:
                raise RuntimeError("database unavailable")

            async def __aexit__(self, *args: object) -> None:
                return None

        class FailingEngine:
            def connect(self) -> FailingConnection:
                return FailingConnection()

        app = FastAPI(title="health-only", lifespan=None)
        app.state.redis_client = None
        app.state.rate_limit_config = RateLimitConfig(
            enabled=True, max_requests=100, window_ms=60000
        )
        app.state.db_engine = FailingEngine()
        app.include_router(health_router)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["db"] == "disconnected"
        assert data["status"] == "degraded"
