from pathlib import Path

from fastapi import APIRouter
from starlette.responses import FileResponse

router = APIRouter()

_PUBLIC_DIR = Path(__file__).resolve().parent.parent.parent / "public"


@router.get("/favicon.ico", include_in_schema=False)
async def favicon_ico() -> FileResponse:
    return FileResponse(_PUBLIC_DIR / "favicon.ico", media_type="image/x-icon")


@router.get("/favicon.png", include_in_schema=False)
async def favicon_png() -> FileResponse:
    return FileResponse(_PUBLIC_DIR / "favicon.png", media_type="image/png")
