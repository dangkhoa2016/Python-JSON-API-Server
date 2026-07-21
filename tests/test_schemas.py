from __future__ import annotations

from app.schemas import TodoResponse, UserResponse, _parse_json_str


class TestParseJsonStr:
    def test_valid_json_string_returns_dict(self) -> None:
        assert _parse_json_str('{"a": 1}') == {"a": 1}

    def test_valid_json_array_returns_list(self) -> None:
        assert _parse_json_str("[1, 2, 3]") == [1, 2, 3]

    def test_valid_json_string_returns_string(self) -> None:
        assert _parse_json_str('"hello"') == "hello"

    def test_int_passthrough(self) -> None:
        assert _parse_json_str(42) == 42

    def test_list_passthrough(self) -> None:
        assert _parse_json_str([1, 2]) == [1, 2]

    def test_none_passthrough(self) -> None:
        assert _parse_json_str(None) is None

    def test_dict_passthrough(self) -> None:
        assert _parse_json_str({"key": "val"}) == {"key": "val"}

    def test_invalid_json_string_returns_string(self) -> None:
        assert _parse_json_str("not json") == "not json"

    def test_empty_string_returns_empty_string(self) -> None:
        assert _parse_json_str("") == ""


class TestUserResponse:
    def test_address_as_dict(self) -> None:
        addr = {"street": "123 Main", "city": "Gotham"}
        user = UserResponse(id=1, address=addr)
        assert user.address == addr

    def test_address_as_json_string(self) -> None:
        addr = '{"street": "123 Main", "city": "Gotham"}'
        user = UserResponse(id=1, address=addr)
        assert user.address == {"street": "123 Main", "city": "Gotham"}

    def test_address_none(self) -> None:
        user = UserResponse(id=1, address=None)
        assert user.address is None

    def test_company_as_dict(self) -> None:
        co = {"name": "Acme", "bs": "innovation"}
        user = UserResponse(id=1, company=co)
        assert user.company == co

    def test_company_as_json_string(self) -> None:
        co = '{"name": "Acme", "bs": "innovation"}'
        user = UserResponse(id=1, company=co)
        assert user.company == {"name": "Acme", "bs": "innovation"}

    def test_company_none(self) -> None:
        user = UserResponse(id=1, company=None)
        assert user.company is None

    def test_default_fields(self) -> None:
        user = UserResponse(id=5)
        assert user.name is None
        assert user.address is None
        assert user.company is None


class TestTodoResponse:
    def test_int_zero_to_false(self) -> None:
        todo = TodoResponse(id=1, completed=0)
        assert todo.completed is False

    def test_int_one_to_true(self) -> None:
        todo = TodoResponse(id=1, completed=1)
        assert todo.completed is True

    def test_int_large_to_true(self) -> None:
        todo = TodoResponse(id=1, completed=42)
        assert todo.completed is True

    def test_bool_true(self) -> None:
        todo = TodoResponse(id=1, completed=True)
        assert todo.completed is True

    def test_bool_false(self) -> None:
        todo = TodoResponse(id=1, completed=False)
        assert todo.completed is False

    def test_string_true_returns_false(self) -> None:
        todo = TodoResponse(id=1, completed="true")
        assert todo.completed is False

    def test_none_returns_false(self) -> None:
        todo = TodoResponse(id=1, completed=None)
        assert todo.completed is False

    def test_default_completed(self) -> None:
        todo = TodoResponse(id=1)
        assert todo.completed is False
