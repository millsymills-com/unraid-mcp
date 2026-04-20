"""Unraid user tools (1 read).

The Unraid API 4.32+ schema dropped ``Query.users``, ``Mutation.addUser``,
and ``Mutation.deleteUser``. The only remaining account-surface is
``Query.me`` (the authenticated user), so this module exposes a single
read tool. Operators who need to create or delete users must do so via
the Unraid WebGUI or the ``unraid-api`` CLI on the server itself.
"""

from __future__ import annotations

from fastmcp import Context, FastMCP

from unraid_mcp.errors import handle_client_error
from unraid_mcp.models.users import UserAccount
from unraid_mcp.tools._helpers import require_client


def register_user_tools(mcp: FastMCP) -> None:
    """Register user tools."""

    @mcp.tool(tags={"users"})
    async def unraid_get_me(ctx: Context) -> UserAccount:
        """Get the authenticated user account (id, name, description, roles).

        Returns info about the account the MCP server's API key belongs to.
        Useful for agents to self-check permissions before attempting writes
        (e.g. inspect ``roles`` for ``ADMIN``).
        """
        try:
            client = require_client(ctx)
            return await client.get_me()
        except Exception as e:
            handle_client_error(e)
