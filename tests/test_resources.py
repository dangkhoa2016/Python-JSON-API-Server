from __future__ import annotations

from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting


class TestListUsers:
    async def test_list_all_users(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/users")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 3
        usernames = {u["username"] for u in data}
        assert usernames == {"Bret", "Antonette", "Samantha"}

    async def test_list_users_default_page_size(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/posts")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) <= 10


class TestListPostsDefaultPageSize:
    async def test_uses_db_setting(self, client: httpx.AsyncClient, test_db: AsyncSession) -> None:
        now = datetime.now(UTC).isoformat()
        test_db.add(
            Setting(
                key="DEFAULT_PAGE_SIZE",
                value="2",
                description="Default page size",
                updated_at=now,
            )
        )
        await test_db.commit()

        resp = await client.get("/api/posts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_falls_back_to_config_when_row_missing(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/posts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5

    async def test_falls_back_to_config_on_invalid_db_value(
        self, client: httpx.AsyncClient, test_db: AsyncSession
    ) -> None:
        now = datetime.now(UTC).isoformat()
        test_db.add(
            Setting(
                key="DEFAULT_PAGE_SIZE",
                value="abc",
                description="Default page size",
                updated_at=now,
            )
        )
        await test_db.commit()

        resp = await client.get("/api/posts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5


class TestGetUser:
    async def test_get_user_by_id(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/users/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert data["username"] == "Bret"
        assert data["email"] == "Sincere@april.biz"

    async def test_get_user_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/users/999")
        assert resp.status_code == 404


class TestNestedRoutes:
    async def test_user_posts(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/users/1/posts")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert all(p["userId"] == 1 for p in data)
        assert len(data) == 3

    async def test_nested_route_404_parent(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/users/999/posts")
        assert resp.status_code == 404

    async def test_nested_route_404_invalid_sub(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/users/1/unknown")
        assert resp.status_code == 404

    async def test_album_photos(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/albums/1/photos")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert all(p["albumId"] == 1 for p in data)
        assert len(data) == 3


class TestCreatePost:
    async def test_create_post(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/posts",
            json={
                "userId": 1,
                "title": "New Post",
                "body": "Post body content",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "New Post"
        assert data["userId"] == 1
        assert data["id"] > 0

    async def test_create_post_auto_id(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/posts",
            json={
                "userId": 1,
                "title": "Auto ID",
                "body": "test",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert isinstance(data["id"], int)

    async def test_create_unknown_table_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/nonexistent", json={"name": "x"})
        assert resp.status_code == 404


class TestUpdatePost:
    async def test_put_full_replace(self, client: httpx.AsyncClient) -> None:
        resp = await client.put(
            "/api/posts/1",
            json={
                "userId": 1,
                "title": "Replaced Title",
                "body": "Replaced body",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Replaced Title"
        assert data["body"] == "Replaced body"

    async def test_put_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.put(
            "/api/posts/999",
            json={
                "userId": 1,
                "title": "x",
                "body": "y",
            },
        )
        assert resp.status_code == 404

    async def test_patch_partial_update(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(
            "/api/posts/1",
            json={
                "title": "Patched Title",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Patched Title"
        assert data["userId"] == 1
        assert data["body"] == "quia et suscipit"

    async def test_patch_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch("/api/posts/999", json={"title": "x"})
        assert resp.status_code == 404


class TestDeletePost:
    async def test_delete_post(self, client: httpx.AsyncClient) -> None:
        resp = await client.delete("/api/posts/1")
        assert resp.status_code == 200
        assert resp.json() == {}

        resp2 = await client.get("/api/posts/1")
        assert resp2.status_code == 404

    async def test_delete_cascade(self, client: httpx.AsyncClient) -> None:
        resp = await client.delete("/api/posts/1")
        assert resp.status_code == 200

        resp2 = await client.get("/api/posts/1/comments")
        assert resp2.status_code == 404

    async def test_delete_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.delete("/api/posts/999")
        assert resp.status_code == 404


class TestFiltering:
    async def test_filter_by_user_id(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/posts?userId=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert all(p["userId"] == 1 for p in data)

    async def test_filter_by_user_id_no_results(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/todos?userId=999")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 0


class TestPagination:
    async def test_pagination(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/posts?_page=1&_limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_pagination_page_2(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/posts?_page=2&_limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_pagination_invalid_page(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/posts?_page=abc")
        assert resp.status_code == 400

    async def test_pagination_invalid_limit(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/posts?_limit=-1")
        assert resp.status_code == 400


class TestSearch:
    async def test_search_posts(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/posts?q=test")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_search_escapes_like_wildcards(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/posts?q=%25")
        assert resp.status_code == 200
        data = resp.json()
        assert data == []


class TestSort:
    async def test_sort_ascending(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/posts?_sort=title&_order=asc")
        assert resp.status_code == 200
        data = resp.json()
        titles = [p["title"] for p in data]
        assert titles == sorted(titles)

    async def test_sort_descending(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/posts?_sort=title&_order=desc")
        assert resp.status_code == 200
        data = resp.json()
        titles = [p["title"] for p in data]
        assert titles == sorted(titles, reverse=True)


class TestNonObjectBody:
    async def test_post_non_object_null(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/posts", content=b"null", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 400

    async def test_put_non_object_null(self, client: httpx.AsyncClient) -> None:
        resp = await client.put(
            "/api/posts/1", content=b"null", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 400

    async def test_patch_non_object_null(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(
            "/api/posts/1", content=b"null", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 400

    async def test_post_non_object_array(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/posts", json=[])
        assert resp.status_code == 400

    async def test_put_non_object_array(self, client: httpx.AsyncClient) -> None:
        resp = await client.put("/api/posts/1", json=[])
        assert resp.status_code == 400

    async def test_patch_non_object_array(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch("/api/posts/1", json=[])
        assert resp.status_code == 400

    async def test_post_non_object_string(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/posts", json="foobar")
        assert resp.status_code == 400

    async def test_put_non_object_string(self, client: httpx.AsyncClient) -> None:
        resp = await client.put("/api/posts/1", json="foobar")
        assert resp.status_code == 400

    async def test_patch_non_object_string(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch("/api/posts/1", json="foobar")
        assert resp.status_code == 400

    async def test_post_non_object_number(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/posts", json=42)
        assert resp.status_code == 400

    async def test_put_non_object_number(self, client: httpx.AsyncClient) -> None:
        resp = await client.put("/api/posts/1", json=42)
        assert resp.status_code == 400

    async def test_patch_non_object_number(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch("/api/posts/1", json=42)
        assert resp.status_code == 400

    async def test_post_non_object_empty(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/posts", content=b"", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 400

    async def test_put_non_object_empty(self, client: httpx.AsyncClient) -> None:
        resp = await client.put(
            "/api/posts/1", content=b"", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 400

    async def test_patch_non_object_empty(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(
            "/api/posts/1", content=b"", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 400


class TestPutReplacement:
    async def test_put_replacement_sets_defaults(self, client: httpx.AsyncClient) -> None:
        resp = await client.put(
            "/api/posts/1",
            json={"title": "Only Title"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Only Title"
        assert data["body"] is None
        assert data["userId"] is None


class TestPatchPartial:
    async def test_patch_partial_one_field(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(
            "/api/posts/1",
            json={"title": "Patched Title"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Patched Title"
        assert data["userId"] == 1
        assert data["body"] == "quia et suscipit"


class TestUnknownTable:
    async def test_unknown_table_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/unknown")
        assert resp.status_code == 404


class TestTrailingSlash:
    async def test_list_users_with_trailing_slash(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/users/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 3

    async def test_trailing_slash_returns_same_data(self, client: httpx.AsyncClient) -> None:
        resp_slash = await client.get("/api/users/")
        resp_plain = await client.get("/api/users")
        assert resp_slash.status_code == 200
        assert resp_slash.json() == resp_plain.json()

    async def test_get_resource_with_trailing_slash(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/users/1/")
        assert resp.status_code == 200
        assert resp.json()["id"] == 1

    async def test_nested_route_with_trailing_slash(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/users/1/posts/")
        assert resp.status_code == 200
        data = resp.json()
        assert all(p["userId"] == 1 for p in data)

    async def test_create_with_trailing_slash(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/posts/",
            json={"userId": 1, "title": "Trailing Slash Post", "body": "Post body content"},
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == "Trailing Slash Post"

    async def test_health_with_trailing_slash(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/health/")
        assert resp.status_code == 200

    async def test_api_root_with_trailing_slash(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/")
        assert resp.status_code == 200

    async def test_root_path_is_not_stripped(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/")
        assert resp.status_code == 200
