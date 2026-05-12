"""User share tools (read-only)."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from unraid_mcp.errors import UnraidNotFoundError
from unraid_mcp.models.shares import Share
from unraid_mcp.tools._helpers import require_client, unraid_tool


def register_share_tools(mcp: FastMCP) -> None:
    """Register share tools."""

    @unraid_tool(mcp, tags={"shares"})
    async def unraid_list_shares(ctx: Context) -> list[Share]:
        """List user shares with capacity, allocator, cache settings, and disk inclusion lists.

        Args:
            ctx: FastMCP request context.

        Returns:
            List of ``Share`` models, one per user share.
        """
        client = require_client(ctx)
        return await client.list_shares()

    @unraid_tool(mcp, tags={"shares"})
    async def unraid_get_share(ctx: Context, name: str) -> Share:
        """Get a specific user share by name.

        Args:
            ctx: FastMCP request context.
            name: Share name.

        Returns:
            ``Share`` model for the matching share.
        """
        client = require_client(ctx)
        shares = await client.list_shares()
        for share in shares:
            if share.name == name:
                return share
        raise UnraidNotFoundError(f"Share '{name}' not found")
