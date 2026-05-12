"""Tool tests for the users domain."""

from __future__ import annotations

from unraid_mcp.models.users import User


class TestGetMe:
    async def test_returns_user(self, client_rw):
        client, mock = client_rw
        mock.get_me.return_value = User(id="u1", name="root", description="admin", roles="admin")
        result = await client.call_tool("unraid_get_me")
        assert result.structured_content["name"] == "root"
        assert result.structured_content["roles"] == "admin"

    async def test_visible_in_readonly(self, client_ro):
        """`unraid_get_me` is a read tool — must be exposed in read-only mode."""
        client, mock = client_ro
        mock.get_me.return_value = User(id="u1", name="alice", roles="user")
        result = await client.call_tool("unraid_get_me")
        assert result.structured_content["name"] == "alice"


class TestUserModelPasswordLeakGuard:
    """Regression guard: `User` must never carry a `password` field (#107/#132)."""

    def test_user_model_has_no_password_field(self):
        assert "password" not in User.model_fields

    def test_user_model_drops_server_pushed_password(self):
        instance = User.model_validate({"id": "u1", "name": "root", "roles": "admin", "password": "$6$shadow"})
        assert "password" not in instance.model_dump()
        assert not hasattr(instance, "password")
        assert instance.model_extra == {} or instance.model_extra is None
