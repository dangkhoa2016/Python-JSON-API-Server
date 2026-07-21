from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, default=None)
    username: Mapped[str | None] = mapped_column(Text, unique=True, default=None)
    email: Mapped[str | None] = mapped_column(Text, default=None)
    phone: Mapped[str | None] = mapped_column(Text, default=None)
    website: Mapped[str | None] = mapped_column(Text, default=None)
    address: Mapped[str | None] = mapped_column(Text, default=None)
    company: Mapped[str | None] = mapped_column(Text, default=None)


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    userId: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), default=None)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    body: Mapped[str | None] = mapped_column(Text, default=None)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    postId: Mapped[int | None] = mapped_column(Integer, ForeignKey("posts.id"), default=None)
    name: Mapped[str | None] = mapped_column(Text, default=None)
    email: Mapped[str | None] = mapped_column(Text, default=None)
    body: Mapped[str | None] = mapped_column(Text, default=None)


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    userId: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), default=None)
    title: Mapped[str | None] = mapped_column(Text, default=None)


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    albumId: Mapped[int | None] = mapped_column(Integer, ForeignKey("albums.id"), default=None)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    url: Mapped[str | None] = mapped_column(Text, default=None)
    thumbnailUrl: Mapped[str | None] = mapped_column(Text, default=None)


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    userId: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), default=None)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[str] = mapped_column(Text, default="")
