from fastapi import APIRouter

from app.routes.resources import PUBLIC_TABLES as TABLES

router = APIRouter()


@router.get("/")
@router.get("/api")
async def info() -> dict[str, object]:
    return {
        "message": "Python JSON API Server — JSONPlaceholder-compatible REST API",
        "version": "1.0.0",
        "endpoints": [f"/api/{t}" for t in TABLES],
        "docs": "GET /health for server status",
    }
