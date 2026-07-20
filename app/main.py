from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.routes.public import router as public_router
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
app = FastAPI(title="python-json-api-server", version="1.0.0", lifespan=lifespan)
app.include_router(public_router)
