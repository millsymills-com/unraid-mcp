"""Tool tests for the users domain (self-introspection only)."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.models.users import UserAccount


class TestGetMe:
    async def test_returns_user_account(self, client_rw):
        client, mock = client_rw
        mock.get_me.return_value = UserAccount(
            id="u1",
            name="alice",
            description="Admin",
            roles=["ADMIN", "CONNECT"],
        )
        result = await client.call_tool("unraid_get_me")
        assert result.structured_content["name"] == "alice"
        assert result.structured_content["roles"] == ["ADMIN", "CONNECT"]

    async def test_visible_in_readonly_mode(self, client_ro):
        # `unraid_get_me` is a read tool; available regardless of mode.
        client, _ = client_ro
        tool_names = {t.name for t in await client.list_tools()}
        assert "unraid_get_me" in tool_names


class TestRemovedUserTools:
    """Regression: the old user-mutation tools were removed from the surface."""

    @pytest.mark.parametrize(
        "removed_tool",
        ["unraid_list_users", "unraid_create_user", "unraid_delete_user"],
    )
    async def test_removed_tool_is_absent(self, client_rw, removed_tool):
        client, _ = client_rw
        tool_names = {t.name for t in await client.list_tools()}
        assert removed_tool not in tool_names, (
            f"{removed_tool} should have been removed; Unraid API 4.32+ dropped the underlying GraphQL surface (#57)."
        )

    async def test_removed_tool_cannot_be_called(self, client_rw):
        client, _ = client_rw
        with pytest.raises(ToolError, match="Unknown tool"):
            await client.call_tool("unraid_create_user", {"name": "x", "password": "y"})
