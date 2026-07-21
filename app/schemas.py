import json
from typing import Any

from pydantic import BaseModel, field_validator


def _parse_json_str(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return v
    return v


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str | None = None
    username: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    address: str | dict | None = None
    company: str | dict | None = None

    @field_validator("address", "company", mode="before")
    @classmethod
    def parse_json_field(cls, v: Any) -> Any:
        return _parse_json_str(v)


class PostResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    userId: int | None = None
    title: str | None = None
    body: str | None = None


class CommentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    postId: int | None = None
    name: str | None = None
    email: str | None = None
    body: str | None = None


class AlbumResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    userId: int | None = None
    title: str | None = None


class PhotoResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    albumId: int | None = None
    title: str | None = None
    url: str | None = None
    thumbnailUrl: str | None = None


class TodoResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    userId: int | None = None
    title: str | None = None
    completed: bool = False

    @field_validator("completed", mode="before")
    @classmethod
    def parse_completed(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return bool(v)
        return False


class UserCreate(BaseModel):
    model_config = {"extra": "forbid"}
    id: int | None = None
    name: str | None = None
    username: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    address: str | dict | None = None
    company: str | dict | None = None


class PostCreate(BaseModel):
    model_config = {"extra": "forbid"}
    id: int | None = None
    userId: int | None = None
    title: str | None = None
    body: str | None = None


class CommentCreate(BaseModel):
    model_config = {"extra": "forbid"}
    id: int | None = None
    postId: int | None = None
    name: str | None = None
    email: str | None = None
    body: str | None = None


class AlbumCreate(BaseModel):
    model_config = {"extra": "forbid"}
    id: int | None = None
    userId: int | None = None
    title: str | None = None


class PhotoCreate(BaseModel):
    model_config = {"extra": "forbid"}
    id: int | None = None
    albumId: int | None = None
    title: str | None = None
    url: str | None = None
    thumbnailUrl: str | None = None


class TodoCreate(BaseModel):
    model_config = {"extra": "forbid"}
    id: int | None = None
    userId: int | None = None
    title: str | None = None
    completed: bool = False


class SettingResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    key: str
    value: str
    description: str = ""
    updated_at: str = ""
