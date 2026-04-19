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
    async def test_forwards_args(self, client_rw_user_mutations):
        client, mock = client_rw_user_mutations
        mock.create_user.return_value = {"addUser": {"id": "u1", "name": "alice"}}
        await client.call_tool(
            "unraid_create_user",
            {"name": "alice", "password": "hunter2", "description": "Admin"},
        )
        mock.create_user.assert_awaited_once_with(name="alice", password="hunter2", description="Admin")

    async def test_omits_description_when_missing(self, client_rw_user_mutations):
        client, mock = client_rw_user_mutations
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

    async def test_hidden_in_rw_without_user_mutations_flag(self, client_rw):
        """Default `client_rw` has UNRAID_ALLOW_USER_MUTATIONS=false → tool must stay hidden."""
        client, _ = client_rw
        with pytest.raises(ToolError, match="Unknown tool"):
            await client.call_tool(
                "unraid_create_user",
                {"name": "x", "password": "y"},
            )


class TestCreateUserPasswordEnvVar:
    async def test_resolves_from_env_var(self, client_rw_user_mutations, monkeypatch):
        client, mock = client_rw_user_mutations
        monkeypatch.setenv("UNRAID_NEW_USER_ALICE_PASSWORD", "secret-from-env")
        mock.create_user.return_value = {"addUser": {"id": "u1", "name": "alice"}}
        await client.call_tool(
            "unraid_create_user",
            {"name": "alice", "password_env_var": "UNRAID_NEW_USER_ALICE_PASSWORD"},
        )
        mock.create_user.assert_awaited_once_with(
            name="alice",
            password="secret-from-env",
            description=None,
        )

    async def test_rejects_both_password_and_env_var(self, client_rw_user_mutations):
        client, _ = client_rw_user_mutations
        with pytest.raises(ToolError, match="exactly one of"):
            await client.call_tool(
                "unraid_create_user",
                {"name": "x", "password": "p", "password_env_var": "UNRAID_NEW_USER_X"},
            )

    async def test_rejects_neither_password_nor_env_var(self, client_rw_user_mutations):
        client, _ = client_rw_user_mutations
        with pytest.raises(ToolError, match="exactly one of"):
            await client.call_tool("unraid_create_user", {"name": "x"})

    async def test_rejects_env_var_outside_prefix(self, client_rw_user_mutations, monkeypatch):
        client, _ = client_rw_user_mutations
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "should-not-be-readable")
        with pytest.raises(ToolError, match="must start with 'UNRAID_NEW_USER_'"):
            await client.call_tool(
                "unraid_create_user",
                {"name": "x", "password_env_var": "AWS_SECRET_ACCESS_KEY"},
            )

    async def test_rejects_unset_env_var(self, client_rw_user_mutations, monkeypatch):
        client, _ = client_rw_user_mutations
        monkeypatch.delenv("UNRAID_NEW_USER_MISSING", raising=False)
        with pytest.raises(ToolError, match="unset or empty"):
            await client.call_tool(
                "unraid_create_user",
                {"name": "x", "password_env_var": "UNRAID_NEW_USER_MISSING"},
            )

    async def test_rejects_empty_env_var(self, client_rw_user_mutations, monkeypatch):
        client, _ = client_rw_user_mutations
        monkeypatch.setenv("UNRAID_NEW_USER_EMPTY", "")
        with pytest.raises(ToolError, match="unset or empty"):
            await client.call_tool(
                "unraid_create_user",
                {"name": "x", "password_env_var": "UNRAID_NEW_USER_EMPTY"},
            )


class TestDeleteUser:
    async def test_forwards_name(self, client_rw_user_mutations):
        client, mock = client_rw_user_mutations
        mock.delete_user.return_value = {"deleteUser": {"name": "bob"}}
        await client.call_tool("unraid_delete_user", {"name": "bob"})
        mock.delete_user.assert_awaited_once_with("bob")

    async def test_hidden_in_rw_without_user_mutations_flag(self, client_rw):
        client, _ = client_rw
        with pytest.raises(ToolError, match="Unknown tool"):
            await client.call_tool("unraid_delete_user", {"name": "bob"})
