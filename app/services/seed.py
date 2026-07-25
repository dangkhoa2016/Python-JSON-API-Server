import json
import time
from typing import Any, TypedDict, cast

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Album, Comment, Photo, Post, Todo, User


class SeedPayload(TypedDict):
    users: list[dict[str, Any]]
    posts: list[dict[str, Any]]
    comments: list[dict[str, Any]]
    albums: list[dict[str, Any]]
    photos: list[dict[str, Any]]
    todos: list[dict[str, Any]]


async def fetch_seed_payload(base_url: str) -> SeedPayload:
    payload: dict[str, list[dict[str, Any]]] = {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        for resource in ("users", "posts", "comments", "albums", "photos", "todos"):
            resp = await client.get(f"{base_url}/{resource}")
            resp.raise_for_status()
            value = resp.json()
            if not isinstance(value, list):
                raise ValueError(f"Invalid {resource} seed payload")
            payload[resource] = value
    return cast(SeedPayload, payload)


def _build_users(users_data: list[dict[str, Any]]) -> list[User]:
    return [
        User(
            id=u["id"],
            name=u.get("name"),
            username=u.get("username"),
            email=u.get("email"),
            phone=u.get("phone"),
            website=u.get("website"),
            address=json.dumps(u.get("address")) if u.get("address") else None,
            company=json.dumps(u.get("company")) if u.get("company") else None,
        )
        for u in users_data
    ]


def _build_posts(posts_data: list[dict[str, Any]]) -> list[Post]:
    return [
        Post(id=p["id"], userId=p.get("userId"), title=p.get("title"), body=p.get("body"))
        for p in posts_data
    ]


def _build_comments(comments_data: list[dict[str, Any]]) -> list[Comment]:
    return [
        Comment(
            id=c["id"],
            postId=c.get("postId"),
            name=c.get("name"),
            email=c.get("email"),
            body=c.get("body"),
        )
        for c in comments_data
    ]


def _build_albums(albums_data: list[dict[str, Any]]) -> list[Album]:
    return [Album(id=a["id"], userId=a.get("userId"), title=a.get("title")) for a in albums_data]


def _build_photos(photos_data: list[dict[str, Any]]) -> list[Photo]:
    return [
        Photo(
            id=ph["id"],
            albumId=ph.get("albumId"),
            title=ph.get("title"),
            url=ph.get("url"),
            thumbnailUrl=ph.get("thumbnailUrl"),
        )
        for ph in photos_data
    ]


def _build_todos(todos_data: list[dict[str, Any]]) -> list[Todo]:
    return [
        Todo(
            id=t["id"],
            userId=t.get("userId"),
            title=t.get("title"),
            completed=t.get("completed", False),
        )
        for t in todos_data
    ]


def add_seed_rows(db: AsyncSession, payload: SeedPayload) -> None:
    for u in _build_users(payload["users"]):
        db.add(u)
    for p in _build_posts(payload["posts"]):
        db.add(p)
    for c in _build_comments(payload["comments"]):
        db.add(c)
    for a in _build_albums(payload["albums"]):
        db.add(a)
    for ph in _build_photos(payload["photos"]):
        db.add(ph)
    for t_item in _build_todos(payload["todos"]):
        db.add(t_item)


async def apply_seed_payload(
    db: AsyncSession,
    payload: SeedPayload,
    *,
    commit: bool = True,
) -> None:
    for u in _build_users(payload["users"]):
        db.add(u)
    await db.flush()

    for p in _build_posts(payload["posts"]):
        db.add(p)
    for a in _build_albums(payload["albums"]):
        db.add(a)
    for t_item in _build_todos(payload["todos"]):
        db.add(t_item)
    await db.flush()

    for c in _build_comments(payload["comments"]):
        db.add(c)
    for ph in _build_photos(payload["photos"]):
        db.add(ph)
    await db.flush()

    if commit:
        await db.commit()


async def seed(db: AsyncSession) -> int:
    row = await db.execute(select(text("COUNT(*)")).select_from(User))
    count = row.scalar_one()
    if count > 0:
        print("[DB] Already seeded, skipping.")
        return 0

    t0 = time.time()
    base = settings.SEED_API_BASE_URL

    payload = await fetch_seed_payload(base)
    await apply_seed_payload(db, payload)

    total = int((time.time() - t0) * 1000)
    print(f"[Seed] Seeding done in {total}ms")
    return (
        len(payload["users"])
        + len(payload["posts"])
        + len(payload["comments"])
        + len(payload["albums"])
        + len(payload["photos"])
        + len(payload["todos"])
    )
