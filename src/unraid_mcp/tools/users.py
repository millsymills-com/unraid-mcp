"""Unraid user tools (1 read).

Drift history: #57 — Unraid 7.2+ removed ``Query.users``, ``addUser``, and
``deleteUser`` from the GraphQL API, so the previous ``unraid_list_users``,
``unraid_create_user``, and ``unraid_delete_user`` tools were dropped. The
remaining account coverage is ``unraid_get_me``, which returns the single
``UserAccount`` matching the API key in use via ``Query.me``.
"""

from __future__ import annotations

from fastmcp import Context, FastMCP

from unraid_mcp.models.users import User
from unraid_mcp.tools._helpers import require_client, unraid_tool


def register_user_tools(mcp: FastMCP) -> None:
    """Register user tools."""

    @unraid_tool(mcp, tags={"users"})
    async def unraid_get_me(ctx: Context) -> User:
        """Get the currently-authenticated Unraid user account.

        Returns the ``UserAccount`` for the API key in use (id, name,
        description, roles). Replaces the removed ``unraid_list_users``
        on Unraid 7.2+, where ``Query.users`` no longer exists.

        Args:
            ctx: FastMCP request context.

        Returns:
            A single ``User`` model for the authenticated account.
        """
        client = require_client(ctx)
        return await client.get_me()
