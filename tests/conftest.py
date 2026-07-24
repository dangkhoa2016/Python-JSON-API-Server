from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest_asyncio
from argon2 import PasswordHasher
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.models import Album, Base, Comment, Photo, Post, Setting, Todo, User
from app.routes.public import router as public_router
from app.routes.health import router as health_router
from app.routes.info import router as info_router
from app.routes.resources import router as resources_router


@pytest_asyncio.fixture
async def test_engine() -> AsyncGenerator[Any, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db(test_engine: Any) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seed_test_data(test_engine: Any) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        users = [
            User(id=1, name="Leanne Graham", username="Bret", email="Sincere@april.biz", phone="1-770-736-8031", website="hildegard.org"),
            User(id=2, name="Ervin Howell", username="Antonette", email="Shanna@melissa.tv", phone="010-692-6593", website="anastasia.net"),
            User(id=3, name="Clementine Bauch", username="Samantha", email="Nathan@yesenia.net", phone="1-463-123-4447", website="ramiro.info"),
        ]
        for u in users:
            session.add(u)
        posts = [
            Post(id=1, userId=1, title="sunt aut facere repellat", body="quia et suscipit"),
            Post(id=2, userId=1, title="qui est esse", body="est rerum tempore"),
            Post(id=3, userId=1, title="ea molestias quasi", body="et iusto sed quo"),
            Post(id=4, userId=2, title="eum et est occaecati", body="ullam et saepe"),
            Post(id=5, userId=3, title="nesciunt quas odio", body="repudiandae veniam"),
        ]
        for p in posts:
            session.add(p)
        comments = [
            Comment(id=1, postId=1, name="id labore ex", email="Eliseo@gardner.biz", body="laudantium enim"),
            Comment(id=2, postId=1, name="quo vero reiciendis", email="Jayne_Kuhic@sydney.com", body="est natus"),
            Comment(id=3, postId=2, name="odio iusto", email="Lucio_Hettinger@annie.ca", body="quo fugit"),
            Comment(id=4, postId=3, name="alias/placeat", email="Conrad@adams.info", body="molestiae"),
            Comment(id=5, postId=5, name="nesciunt omnis", email="Telly_Hoeger@billy.biz", body="vitae"),
        ]
        for c in comments:
            session.add(c)
        albums = [
            Album(id=1, userId=1, title="quidem molestiae"),
            Album(id=2, userId=2, title="sunt qui repudiandae"),
        ]
        for a in albums:
            session.add(a)
        photos = [
            Photo(id=1, albumId=1, title="accusamus beatae", url="https://via.placeholder.com/600/92c952", thumbnailUrl="https://via.placeholder.com/150/92c952"),
            Photo(id=2, albumId=1, title="reprehenderit est", url="https://via.placeholder.com/600/771774", thumbnailUrl="https://via.placeholder.com/150/771774"),
            Photo(id=3, albumId=2, title="officia porro", url="https://via.placeholder.com/600/24f355", thumbnailUrl="https://via.placeholder.com/150/24f355"),
            Photo(id=4, albumId=2, title="culpa odio", url="https://via.placeholder.com/600/d32776", thumbnailUrl="https://via.placeholder.com/150/d32776"),
            Photo(id=5, albumId=1, title="natus impedit", url="https://via.placeholder.com/600/56a8c2", thumbnailUrl="https://via.placeholder.com/150/56a8c2"),
        ]
        for ph in photos:
            session.add(ph)
        todos = [
            Todo(id=1, userId=1, title="delectus aut autem", completed=0),
            Todo(id=2, userId=1, title="quis ut nam facilis", completed=1),
            Todo(id=3, userId=2, title="fugiat veniam adipisci", completed=0),
            Todo(id=4, userId=2, title="tempora quo necessitatibus", completed=0),
            Todo(id=5, userId=3, title="et porro tempora", completed=1),
        ]
        for t in todos:
            session.add(t)
        ph = PasswordHasher()
        now = datetime.now(UTC).isoformat()
        admin_key_hash = ph.hash("test-admin-key")
        settings_data = [
            Setting(key="ADMIN_KEY", value=admin_key_hash, description="Admin key", updated_at=now),
            Setting(key="APP_ENV", value="test", description="Environment", updated_at=now),
            Setting(key="PORT", value="3000", description="Port", updated_at=now),
            Setting(key="RATE_LIMIT_ENABLED", value="true", description="Rate limit enabled", updated_at=now),
            Setting(key="RATE_LIMIT_MAX", value="100", description="Rate limit max requests", updated_at=now),
            Setting(key="RATE_LIMIT_WINDOW_MS", value="60000", description="Rate limit window ms", updated_at=now),
            Setting(key="REDIS_HOST", value="127.0.0.1", description="Redis host", updated_at=now),
            Setting(key="REDIS_PORT", value="6379", description="Redis port", updated_at=now),
            Setting(key="REDIS_DB", value="0", description="Redis db", updated_at=now),
            Setting(key="REDIS_PASSWORD", value="placeholder", description="Redis password", updated_at=now),
            Setting(key="REDIS_URL", value="", description="Redis URL", updated_at=now),
        ]
        for s in settings_data:
            session.add(s)
        await session.commit()
        yield session


@pytest_asyncio.fixture
async def test_app(test_engine: Any, seed_test_data: AsyncSession) -> Any:
    app = FastAPI(title="test-app", lifespan=None)
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    from app.services.runtime_config import RateLimitConfig

    app.state.redis_client = None
    app.state.rate_limit_config = RateLimitConfig(enabled=True, max_requests=100, window_ms=60000)
    app.state.db_engine = test_engine
    app.include_router(public_router)
    app.include_router(health_router)
    app.include_router(info_router)
    app.include_router(resources_router)
    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(test_app: Any) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
