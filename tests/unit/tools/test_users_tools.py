"""Tool tests for the users domain."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.models.users import User


class TestListUsers:
    async def test_returns_list(self, client_rw):
        client, mock = client_rw
        mock.list_users.return_value = [User(id="u1", name="alice"), User(id="u2", name="bob")]
        result = await client.call_tool("unraid_list_users")
        assert [u["name"] for u in result.structured_content["result"]] == ["alice", "bob"]


class TestCreateUser:
    async def test_forwards_args(self, client_rw):
        client, mock = client_rw
        mock.create_user.return_value = {"addUser": {"id": "u1", "name": "alice"}}
        await client.call_tool(
            "unraid_create_user",
            {"name": "alice", "password": "hunter2", "description": "Admin"},
        )
        mock.create_user.assert_awaited_once_with(name="alice", password="hunter2", description="Admin")

    async def test_omits_description_when_missing(self, client_rw):
        client, mock = client_rw
        mock.create_user.return_value = {"addUser": {"id": "u1", "name": "bob"}}
        await client.call_tool("unraid_create_user", {"name": "bob", "password": "hunter2"})
        mock.create_user.assert_awaited_once_with(name="bob", password="hunter2", description=None)

    async def test_hidden_in_readonly(self, client_ro):
        client, _ = client_ro
        with pytest.raises(ToolError, match="Unknown tool"):
            await client.call_tool(
                "unraid_create_user",
                {"name": "x", "password": "y"},
            )


class TestDeleteUser:
    async def test_forwards_name(self, client_rw):
        client, mock = client_rw
        mock.delete_user.return_value = {"deleteUser": {"name": "bob"}}
        await client.call_tool("unraid_delete_user", {"name": "bob"})
        mock.delete_user.assert_awaited_once_with("bob")
