import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import (
    Album,
    Base,
    Comment,
    Photo,
    Post,
    Todo,
    User,
)
from app.schemas import (
    AlbumCreate,
    CommentCreate,
    PhotoCreate,
    PostCreate,
    TodoCreate,
    UserCreate,
)
from app.services.runtime_settings import default_page_size

router = APIRouter(prefix="/api")

PUBLIC_TABLES = ("users", "posts", "comments", "albums", "photos", "todos")

MODEL_MAP: dict[str, type[Base]] = {
    "users": User,
    "posts": Post,
    "comments": Comment,
    "albums": Album,
    "photos": Photo,
    "todos": Todo,
}

FILTER_COLS: dict[str, list[str]] = {
    "users": ["id", "name", "username", "email", "phone", "website"],
    "posts": ["id", "userId", "title"],
    "comments": ["id", "postId", "name", "email"],
    "albums": ["id", "userId", "title"],
    "photos": ["id", "albumId", "title", "url", "thumbnailUrl"],
    "todos": ["id", "userId", "title", "completed"],
}

SEARCH_COLS: dict[str, list[str]] = {
    "users": ["name", "username", "email"],
    "posts": ["title", "body"],
    "comments": ["name", "email", "body"],
    "albums": ["title"],
    "photos": ["title"],
    "todos": ["title"],
}

NESTED: dict[str, dict[str, str]] = {
    "users": {"posts": "userId", "albums": "userId", "todos": "userId"},
    "posts": {"comments": "postId"},
    "albums": {"photos": "albumId"},
}

CASCADE_MAP: dict[str, dict[str, Any]] = {
    "users": {"key": "userId", "children": ["posts", "albums", "todos"]},
    "posts": {"key": "postId", "children": ["comments"]},
    "albums": {"key": "albumId", "children": ["photos"]},
}

CREATE_SCHEMA_MAP: dict[str, type[BaseModel]] = {
    "users": UserCreate,
    "posts": PostCreate,
    "comments": CommentCreate,
    "albums": AlbumCreate,
    "photos": PhotoCreate,
    "todos": TodoCreate,
}


def _row_to_dict(row: Base) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        if col.name in ("address", "company") and isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
        if col.name == "completed":
            val = bool(val)
        d[col.name] = val
    return d


def _serialize_value(val: Any) -> Any:
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    return val


async def _cascade_delete(db: AsyncSession, table: str, record_id: int) -> None:
    cascade = CASCADE_MAP.get(table)
    if not cascade:
        return
    fk_key = cascade["key"]
    for child_table in cascade["children"]:
        child_model = MODEL_MAP[child_table]
        fk_col = getattr(child_model, fk_key, None)
        if fk_col is None:
            continue
        child_rows = await db.execute(
            select(child_model.id).where(fk_col == record_id)  # type: ignore[attr-defined]  # SQLAlchemy model class
        )
        child_ids = child_rows.scalars().all()
        for child_id in child_ids:
            await _cascade_delete(db, child_table, child_id)
        await db.execute(delete(child_model).where(fk_col == record_id))


async def _parse_body(
    request: Request, table: str, *, exclude_unset: bool = False
) -> dict[str, Any]:
    body_bytes = await request.body()
    if len(body_bytes) > settings.MAX_BODY_SIZE:
        raise HTTPException(status_code=413, detail="Request body too large")

    try:
        body = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from None

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    schema = CREATE_SCHEMA_MAP.get(table)
    if schema is not None:
        try:
            validated = schema(**body)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors(include_url=False)) from e
        return validated.model_dump(exclude_unset=exclude_unset)

    return body


async def _query_resources(
    db: AsyncSession,
    model: type[Base],
    table: str,
    params: dict[str, str],
    extra_conditions: list | None = None,
) -> list[dict[str, Any]]:
    cols = FILTER_COLS.get(table, [])
    search_cols = SEARCH_COLS.get(table, [])

    page = params.pop("_page", None)
    limit = params.pop("_limit", None)
    start = params.pop("_start", None)
    end = params.pop("_end", None)
    sort_col = params.pop("_sort", None)
    order = params.pop("_order", None)
    search = params.pop("q", None)

    for pname, pval in [("_page", page), ("_limit", limit), ("_start", start), ("_end", end)]:
        if pval is not None:
            if pval == "":
                continue
            try:
                ival = int(pval)
                if ival < 0:
                    raise HTTPException(
                        status_code=400, detail=f"Invalid {pname}: must be a non-negative integer"
                    )
                if pname in ("_page", "_limit") and ival < 1:
                    raise HTTPException(
                        status_code=400, detail=f"Invalid {pname}: must be a positive integer"
                    )
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid {pname}: must be a non-negative integer"
                ) from None

    conditions = list(extra_conditions or [])

    for k, v in params.items():
        if k in cols:
            col_attr = getattr(model, k, None)
            if col_attr is not None:
                if k == "completed":
                    conditions.append(col_attr == (v == "true"))
                else:
                    conditions.append(col_attr == v)

    if search and search_cols:
        search_conditions = []
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like_val = f"%{escaped}%"
        for sc in search_cols:
            col_attr = getattr(model, sc, None)
            if col_attr is not None:
                search_conditions.append(col_attr.like(like_val, escape="\\"))
        if search_conditions:
            conditions.append(or_(*search_conditions))

    query = select(model)
    if conditions:
        query = query.where(and_(*conditions))

    if sort_col and sort_col in cols:
        col_attr = getattr(model, sort_col, None)
        if col_attr is not None:
            if order and order.lower() == "desc":
                query = query.order_by(col_attr.desc())
            else:
                query = query.order_by(col_attr.asc())

    if start is not None and start != "":
        start_val = int(start)
        if end is not None and end != "":
            end_val = int(end)
            query = query.offset(start_val).limit(min(end_val - start_val, settings.MAX_PAGE_SIZE))
        else:
            query = query.offset(start_val)
    else:
        p = int(page) if page and page != "" else 1
        if limit and limit != "":
            lim = min(int(limit), settings.MAX_PAGE_SIZE)
        else:
            lim = min(await default_page_size(db), settings.MAX_PAGE_SIZE)
        query = query.offset((p - 1) * lim).limit(lim)

    result = await db.execute(query)
    rows = result.scalars().all()
    return [_row_to_dict(r) for r in rows]


@router.get("/{table}")
async def list_resources(
    request: Request,
    table: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[dict[str, Any]]:
    if table not in PUBLIC_TABLES:
        raise HTTPException(status_code=404, detail=f"Unknown table: {table}")

    params = dict(request.query_params)
    model = MODEL_MAP[table]
    return await _query_resources(db, model, table, params)


@router.get("/{table}/{record_id}/{sub}")
async def get_nested(
    table: str,
    record_id: int,
    sub: str,
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[dict[str, Any]]:
    if table not in PUBLIC_TABLES:
        raise HTTPException(status_code=404, detail=f"Unknown table: {table}")

    parent_model = MODEL_MAP[table]
    result = await db.execute(select(parent_model).where(parent_model.id == record_id))  # type: ignore[attr-defined]  # SQLAlchemy model class
    parent = result.scalar_one_or_none()
    if parent is None:
        raise HTTPException(status_code=404, detail="Not Found")

    fk_map = NESTED.get(table, {})
    if sub not in fk_map:
        raise HTTPException(status_code=404, detail=f"No nested route '{sub}' under '{table}'")

    child_model = MODEL_MAP.get(sub)
    if child_model is None:
        raise HTTPException(status_code=404, detail=f"Unknown table: {sub}")

    fk_col_name = fk_map[sub]
    fk_col = getattr(child_model, fk_col_name, None)
    if fk_col is None:
        raise HTTPException(status_code=404, detail=f"Unknown foreign key: {fk_col_name}")

    params = dict(request.query_params)
    return await _query_resources(
        db, child_model, sub, params, extra_conditions=[fk_col == record_id]
    )


@router.get("/{table}/{record_id}")
async def get_resource(
    table: str,
    record_id: int,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    if table not in PUBLIC_TABLES:
        raise HTTPException(status_code=404, detail=f"Unknown table: {table}")

    model = MODEL_MAP[table]
    result = await db.execute(select(model).where(model.id == record_id))  # type: ignore[attr-defined]
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return _row_to_dict(row)


@router.post("/{table}", status_code=201)
async def create_resource(
    table: str,
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    if table not in PUBLIC_TABLES:
        raise HTTPException(status_code=404, detail=f"Unknown table: {table}")

    body = await _parse_body(request, table)

    model = MODEL_MAP[table]
    col_names = {c.name for c in model.__table__.columns}
    insert_data = {k: _serialize_value(v) for k, v in body.items() if k in col_names and k != "id"}
    if body.get("id") is not None:
        insert_data["id"] = body["id"]

    record = model(**insert_data)
    db.add(record)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Conflict: {table} record violates a unique or foreign key constraint",
        ) from exc
    await db.refresh(record)
    return _row_to_dict(record)


@router.put("/{table}/{record_id}")
async def update_resource(
    table: str,
    record_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    if table not in PUBLIC_TABLES:
        raise HTTPException(status_code=404, detail=f"Unknown table: {table}")

    body = await _parse_body(request, table, exclude_unset=False)

    model = MODEL_MAP[table]
    result = await db.execute(select(model).where(model.id == record_id))  # type: ignore[attr-defined]
    existing = result.scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail="Not Found")

    merged = {**body, "id": record_id}
    col_names = {c.name for c in model.__table__.columns}
    update_data = {
        k: _serialize_value(v) for k, v in merged.items() if k in col_names and k != "id"
    }

    if update_data:
        try:
            await db.execute(update(model).where(model.id == record_id).values(**update_data))  # type: ignore[attr-defined]  # SQLAlchemy model class
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"Conflict: {table} record violates a unique or foreign key constraint",
            ) from exc

    result = await db.execute(select(model).where(model.id == record_id))  # type: ignore[attr-defined]
    updated = result.scalar_one()
    return _row_to_dict(updated)


@router.patch("/{table}/{record_id}")
async def patch_resource(
    table: str,
    record_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    if table not in PUBLIC_TABLES:
        raise HTTPException(status_code=404, detail=f"Unknown table: {table}")

    body = await _parse_body(request, table, exclude_unset=True)

    model = MODEL_MAP[table]
    result = await db.execute(select(model).where(model.id == record_id))  # type: ignore[attr-defined]
    existing = result.scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail="Not Found")

    existing_dict = _row_to_dict(existing)
    merged = {**existing_dict, **body, "id": record_id}
    col_names = {c.name for c in model.__table__.columns}
    update_data = {
        k: _serialize_value(v) for k, v in merged.items() if k in col_names and k != "id"
    }

    try:
        await db.execute(update(model).where(model.id == record_id).values(**update_data))  # type: ignore[attr-defined]  # SQLAlchemy model class
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Conflict: {table} record violates a unique or foreign key constraint",
        ) from exc

    result = await db.execute(select(model).where(model.id == record_id))  # type: ignore[attr-defined]
    updated = result.scalar_one()
    return _row_to_dict(updated)


@router.delete("/{table}/{record_id}")
async def delete_resource(
    table: str,
    record_id: int,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    if table not in PUBLIC_TABLES:
        raise HTTPException(status_code=404, detail=f"Unknown table: {table}")

    model = MODEL_MAP[table]
    result = await db.execute(select(model).where(model.id == record_id))  # type: ignore[attr-defined]
    existing = result.scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail="Not Found")

    await _cascade_delete(db, table, record_id)
    await db.execute(delete(model).where(model.id == record_id))  # type: ignore[attr-defined]
    await db.commit()
    return {}
