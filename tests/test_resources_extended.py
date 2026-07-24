from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import httpx

from app.config import settings
from app.models import Todo, User
from app.routes.resources import (
    _cascade_delete,
    _parse_body,
    _row_to_dict,
    _serialize_value,
)


class TestRowToDict:
    def test_invalid_json_address_field(self, seed_test_data):
        user = User(
            id=99,
            name="Test",
            username="test99",
            email="t@t.com",
            address="not-valid-json{",
            company=None,
        )
        result = _row_to_dict(user)
        assert result["address"] == "not-valid-json{"

    def test_valid_json_address_field(self, seed_test_data):
        user = User(
            id=99,
            name="Test",
            username="test99",
            email="t@t.com",
            address='{"city": "NYC"}',
            company=None,
        )
        result = _row_to_dict(user)
        assert result["address"] == {"city": "NYC"}

    def test_valid_json_company_field(self, seed_test_data):
        user = User(
            id=99,
            name="Test",
            username="test99",
            email="t@t.com",
            address=None,
            company='{"name": "Acme"}',
        )
        result = _row_to_dict(user)
        assert result["company"] == {"name": "Acme"}

    def test_completed_field_bool_conversion(self, seed_test_data):
        todo = Todo(id=99, userId=1, title="test", completed=1)
        result = _row_to_dict(todo)
        assert result["completed"] is True

    def test_completed_field_false_conversion(self, seed_test_data):
        todo = Todo(id=99, userId=1, title="test", completed=0)
        result = _row_to_dict(todo)
        assert result["completed"] is False

    def test_null_address_stays_none(self, seed_test_data):
        user = User(
            id=99, name="Test", username="test99", email="t@t.com", address=None, company=None
        )
        result = _row_to_dict(user)
        assert result["address"] is None


class TestSerializeValue:
    def test_dict_to_json_string(self):
        result = _serialize_value({"key": "value"})
        assert result == json.dumps({"key": "value"})

    def test_list_to_json_string(self):
        result = _serialize_value([1, 2, 3])
        assert result == json.dumps([1, 2, 3])

    def test_bool_true_to_1(self):
        assert _serialize_value(True) == 1

    def test_bool_false_to_0(self):
        assert _serialize_value(False) == 0

    def test_string_passthrough(self):
        assert _serialize_value("hello") == "hello"

    def test_int_passthrough(self):
        assert _serialize_value(42) == 42

    def test_none_passthrough(self):
        assert _serialize_value(None) is None


class TestCascadeDelete:
    async def test_no_cascade_map(self, test_db):
        await _cascade_delete(test_db, "todos", 1)

    async def test_cascade_users(self, test_db, seed_test_data):
        await _cascade_delete(test_db, "users", 1)
        await test_db.commit()

    async def test_cascade_skips_child_missing_fk_column(
        self, test_db, seed_test_data, monkeypatch
    ):
        from app.routes.resources import MODEL_MAP

        monkeypatch.setitem(MODEL_MAP, "comments", Todo)
        await _cascade_delete(test_db, "posts", 1)


class _FakeRequest:
    def __init__(self, body: bytes) -> None:
        self._body = body

    async def body(self) -> bytes:
        return self._body


class TestParseBody:
    async def test_no_schema_returns_raw_body(self, monkeypatch) -> None:
        from app.routes.resources import CREATE_SCHEMA_MAP

        monkeypatch.setitem(CREATE_SCHEMA_MAP, "posts", None)
        result = await _parse_body(_FakeRequest(b'{"title":"x"}'), "posts")
        assert result == {"title": "x"}


class TestListResourcesUnknownTable:
    async def test_unknown_table_404(self, client: httpx.AsyncClient):
        resp = await client.get("/api/nonexistent")
        assert resp.status_code == 404


class TestGetResource:
    async def test_unknown_table(self, client: httpx.AsyncClient):
        resp = await client.get("/api/nonexistent/1")
        assert resp.status_code == 404

    async def test_non_existent_id(self, client: httpx.AsyncClient):
        resp = await client.get("/api/users/99999")
        assert resp.status_code == 404

    async def test_valid_get(self, client: httpx.AsyncClient):
        resp = await client.get("/api/users/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1


class TestNestedRoutesExtended:
    async def test_unknown_parent_table(self, client: httpx.AsyncClient):
        resp = await client.get("/api/nonexistent/1/posts")
        assert resp.status_code == 404

    async def test_unknown_sub_route(self, client: httpx.AsyncClient):
        resp = await client.get("/api/users/1/unknown")
        assert resp.status_code == 404

    async def test_invalid_foreign_key(self, client: httpx.AsyncClient):
        resp = await client.get("/api/posts/1/nonexistent")
        assert resp.status_code == 404

    async def test_nested_child_model_not_in_model_map(self, client: httpx.AsyncClient):
        from app.routes.resources import NESTED

        fake_nested = {**NESTED, "users": {**NESTED.get("users", {}), "orphan": "userId"}}
        with patch("app.routes.resources.NESTED", fake_nested):
            resp = await client.get("/api/users/1/orphan")
            assert resp.status_code == 404

    async def test_nested_fk_col_not_on_model(self, client: httpx.AsyncClient):
        from app.routes.resources import NESTED

        fake_nested = {
            **NESTED,
            "users": {**NESTED.get("users", {}), "posts": "nonexistent_fk_col"},
        }
        with patch("app.routes.resources.NESTED", fake_nested):
            resp = await client.get("/api/users/1/posts")
            assert resp.status_code == 404


class TestCreateResource:
    async def test_body_too_large(self, client: httpx.AsyncClient):
        large_body = json.dumps({"title": "x" * (settings.MAX_BODY_SIZE + 1)})
        resp = await client.post(
            "/api/posts", content=large_body, headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 413

    async def test_invalid_json(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/posts", content=b"not json", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 400

    async def test_null_json_body(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/posts", content=b"null", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 400

    async def test_list_body(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/posts",
            content=json.dumps([1, 2, 3]),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    async def test_empty_body(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/posts", content=b"", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 400

    async def test_create_with_dict_field(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/users",
            json={
                "name": "Test User",
                "username": "testdict",
                "address": {"city": "NYC", "street": "Main St"},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["address"] == {"city": "NYC", "street": "Main St"}

    async def test_create_with_bool_field(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/todos",
            json={
                "userId": 1,
                "title": "Test todo",
                "completed": True,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["completed"] is True

    async def test_create_with_bool_false(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/todos",
            json={
                "userId": 1,
                "title": "Test todo",
                "completed": False,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["completed"] is False

    async def test_create_unknown_table(self, client: httpx.AsyncClient):
        resp = await client.post("/api/nonexistent", json={"name": "x"})
        assert resp.status_code == 404

    async def test_create_auto_id(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/posts",
            json={
                "userId": 1,
                "title": "Auto ID Test",
                "body": "test body",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] > 0

    async def test_create_with_explicit_id(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/users",
            json={
                "id": 99,
                "name": "Explicit ID User",
                "username": "explicit-id",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == 99

    async def test_create_rejects_unknown_fields(self, client: httpx.AsyncClient):
        response = await client.post(
            "/api/posts",
            json={"userId": 1, "title": "title", "body": "body", "admin": True},
        )
        assert response.status_code == 422

    async def test_concurrent_creates_receive_distinct_ids(self, client: httpx.AsyncClient):
        responses = await asyncio.gather(
            *(
                client.post(
                    "/api/posts",
                    json={"userId": 1, "title": f"post-{i}", "body": "body"},
                )
                for i in range(20)
            )
        )
        assert all(response.status_code == 201 for response in responses)
        ids = [response.json()["id"] for response in responses]
        assert len(ids) == len(set(ids))


class TestUpdateResource:
    async def test_unknown_table(self, client: httpx.AsyncClient):
        resp = await client.put("/api/nonexistent/1", json={"name": "x"})
        assert resp.status_code == 404

    async def test_body_too_large(self, client: httpx.AsyncClient):
        large_body = json.dumps({"title": "x" * (settings.MAX_BODY_SIZE + 1)})
        resp = await client.put(
            "/api/posts/1", content=large_body, headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 413

    async def test_invalid_json(self, client: httpx.AsyncClient):
        resp = await client.put(
            "/api/posts/1", content=b"not json", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 400

    async def test_null_json_body(self, client: httpx.AsyncClient):
        resp = await client.put(
            "/api/posts/1", content=b"null", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 400

    async def test_not_found(self, client: httpx.AsyncClient):
        resp = await client.put("/api/posts/99999", json={"title": "x"})
        assert resp.status_code == 404

    async def test_put_duplicate_username_returns_409(self, client: httpx.AsyncClient):
        resp = await client.put(
            "/api/users/1",
            json={"username": "Antonette"},
        )
        assert resp.status_code == 409

    async def test_full_update(self, client: httpx.AsyncClient):
        resp = await client.put(
            "/api/posts/1",
            json={
                "userId": 1,
                "title": "Replaced",
                "body": "New body",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Replaced"
        assert data["body"] == "New body"

    async def test_put_rejects_array_body(self, client: httpx.AsyncClient):
        response = await client.put("/api/posts/1", json=[])
        assert response.status_code == 400


class TestPatchResource:
    async def test_unknown_table(self, client: httpx.AsyncClient):
        resp = await client.patch("/api/nonexistent/1", json={"name": "x"})
        assert resp.status_code == 404

    async def test_body_too_large(self, client: httpx.AsyncClient):
        large_body = json.dumps({"title": "x" * (settings.MAX_BODY_SIZE + 1)})
        resp = await client.patch(
            "/api/posts/1", content=large_body, headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 413

    async def test_invalid_json(self, client: httpx.AsyncClient):
        resp = await client.patch(
            "/api/posts/1", content=b"not json", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 400

    async def test_null_json_body(self, client: httpx.AsyncClient):
        resp = await client.patch(
            "/api/posts/1", content=b"null", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 400

    async def test_not_found(self, client: httpx.AsyncClient):
        resp = await client.patch("/api/posts/99999", json={"title": "x"})
        assert resp.status_code == 404

    async def test_partial_update(self, client: httpx.AsyncClient):
        resp = await client.patch("/api/posts/1", json={"title": "Patched"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Patched"
        assert data["userId"] == 1

    async def test_patch_rejects_scalar_body(self, client: httpx.AsyncClient):
        response = await client.patch(
            "/api/posts/1",
            content="42",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400


class TestDeleteResource:
    async def test_unknown_table(self, client: httpx.AsyncClient):
        resp = await client.delete("/api/nonexistent/1")
        assert resp.status_code == 404

    async def test_not_found(self, client: httpx.AsyncClient):
        resp = await client.delete("/api/posts/99999")
        assert resp.status_code == 404

    async def test_successful_delete(self, client: httpx.AsyncClient):
        resp = await client.delete("/api/posts/1")
        assert resp.status_code == 200
        assert resp.json() == {}

    async def test_delete_cascade_user(self, client: httpx.AsyncClient):
        resp = await client.delete("/api/users/2")
        assert resp.status_code == 200
        resp2 = await client.get("/api/posts/4")
        assert resp2.status_code == 404

    async def test_delete_cascade_post(self, client: httpx.AsyncClient):
        resp = await client.delete("/api/posts/1")
        assert resp.status_code == 200

    async def test_delete_cascade_album(self, client: httpx.AsyncClient):
        resp = await client.delete("/api/albums/1")
        assert resp.status_code == 200


class TestDeleteUserCascade:
    async def test_delete_user_removes_grandchild_rows(self, client: httpx.AsyncClient):
        resp = await client.delete("/api/users/1")
        assert resp.status_code == 200

        for path in [
            "/api/users/1",
            "/api/posts/1",
            "/api/comments/1",
            "/api/albums/1",
            "/api/photos/1",
            "/api/todos/1",
        ]:
            check = await client.get(path)
            assert check.status_code == 404, f"{path} should be gone after user cascade delete"


class TestCreateConflict:
    async def test_create_duplicate_username_returns_409(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/users",
            json={"name": "Copy", "username": "Bret", "email": "copy@example.com"},
        )
        assert resp.status_code == 409

    async def test_patch_duplicate_username_returns_409(self, client: httpx.AsyncClient):
        resp = await client.patch("/api/users/2", json={"username": "Bret"})
        assert resp.status_code == 409

    async def test_session_usable_after_conflict(self, client: httpx.AsyncClient):
        conflicted = await client.post(
            "/api/users",
            json={"name": "Copy", "username": "Bret", "email": "copy@example.com"},
        )
        assert conflicted.status_code == 409

        resp = await client.post(
            "/api/users",
            json={"name": "Fresh", "username": "freshuser", "email": "fresh@example.com"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "freshuser"


class TestFilteringExtended:
    async def test_completed_true_filter(self, client: httpx.AsyncClient):
        resp = await client.get("/api/todos?completed=true")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        assert all(t["completed"] is True for t in data)

    async def test_completed_false_filter(self, client: httpx.AsyncClient):
        resp = await client.get("/api/todos?completed=false")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        assert all(t["completed"] is False for t in data)


class TestPaginationExtended:
    async def test_start_end_pagination(self, client: httpx.AsyncClient):
        resp = await client.get("/api/posts?_start=1&_end=3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_start_only(self, client: httpx.AsyncClient):
        resp = await client.get("/api/posts?_start=2")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_default_page_limit(self, client: httpx.AsyncClient):
        resp = await client.get("/api/posts")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_invalid_negative_page(self, client: httpx.AsyncClient):
        resp = await client.get("/api/posts?_page=-1")
        assert resp.status_code == 400

    async def test_invalid_negative_limit(self, client: httpx.AsyncClient):
        resp = await client.get("/api/posts?_limit=-1")
        assert resp.status_code == 400

    async def test_invalid_zero_page(self, client: httpx.AsyncClient):
        resp = await client.get("/api/posts?_page=0")
        assert resp.status_code == 400

    async def test_invalid_zero_limit(self, client: httpx.AsyncClient):
        resp = await client.get("/api/posts?_limit=0")
        assert resp.status_code == 400

    async def test_empty_pagination_param_ignored(self, client: httpx.AsyncClient):
        resp = await client.get("/api/posts?_page=&_limit=")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_limit_capped_at_max_page_size(self, client: httpx.AsyncClient):
        from app.config import settings

        resp = await client.get(f"/api/posts?_limit={settings.MAX_PAGE_SIZE + 500}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) <= settings.MAX_PAGE_SIZE

    async def test_start_end_window_capped_at_max_page_size(self, client: httpx.AsyncClient):
        from app.config import settings

        start = settings.MAX_PAGE_SIZE + 1
        resp = await client.get(f"/api/posts?_start=0&_end={start + 500}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) <= settings.MAX_PAGE_SIZE

    async def test_nested_route_child_model_none(self, client: httpx.AsyncClient):
        resp = await client.get("/api/users/1/nonexistent_table")
        assert resp.status_code == 404


class TestSettingsAreNotPublic:
    async def test_list_settings_is_not_a_public_resource(self, client):
        response = await client.get("/api/settings")
        assert response.status_code == 404

    async def test_get_setting_is_not_a_public_resource(self, client):
        response = await client.get("/api/settings/1")
        assert response.status_code == 404

    async def test_create_setting_is_not_a_public_resource(self, client):
        response = await client.post(
            "/api/settings",
            json={"key": "ADMIN_KEY", "value": "attacker-value"},
        )
        assert response.status_code == 404

    async def test_update_setting_is_not_a_public_resource(self, client):
        response = await client.patch(
            "/api/settings/1",
            json={"value": "attacker-value"},
        )
        assert response.status_code == 404

    async def test_delete_setting_is_not_a_public_resource(self, client):
        response = await client.delete("/api/settings/1")
        assert response.status_code == 404
