"""Unraid user tools (1 read + 2 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unraid_mcp.errors import handle_client_error
from unraid_mcp.tools._helpers import require_client, require_readwrite


def register_user_tools(mcp: FastMCP) -> None:
    """Register user tools."""

    @mcp.tool(tags={"users"})
    async def unraid_list_users(ctx: Context) -> list[dict[str, Any]]:
        """List Unraid users (id, name, description, roles)."""
        try:
            client = require_client(ctx)
            return await client.list_users()
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "users"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unraid_create_user(
        ctx: Context,
        name: str,
        password: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Unraid user.

        Args:
            name: Username (must be unique).
            password: Initial password.
            description: Optional description shown in the WebGUI.
        """
        try:
            client = require_readwrite(ctx, "create user")
            return await client.create_user(name=name, password=password, description=description)
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "users"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    async def unraid_delete_user(ctx: Context, name: str) -> dict[str, Any]:
        """Delete an Unraid user by name.

        Args:
            name: Username to delete.
        """
        try:
            client = require_readwrite(ctx, "delete user")
            return await client.delete_user(name)
        except Exception as e:
            handle_client_error(e)
