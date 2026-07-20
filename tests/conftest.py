import httpx
import pytest_asyncio
from fastapi import FastAPI
from app.routes.public import router as public_router
@pytest_asyncio.fixture
async def client():
    app = FastAPI(title="test-app")
    app.include_router(public_router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
