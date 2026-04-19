"""User share tools (read-only)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unraid_mcp.errors import handle_client_error
from unraid_mcp.tools._helpers import require_client


def register_share_tools(mcp: FastMCP) -> None:
    """Register share tools."""

    @mcp.tool(tags={"shares"})
    async def unraid_list_shares(ctx: Context) -> list[dict[str, Any]]:
        """List user shares with capacity, allocator, cache settings, and disk inclusion lists."""
        try:
            client = require_client(ctx)
            return await client.list_shares()
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"shares"})
    async def unraid_get_share(ctx: Context, name: str) -> dict[str, Any]:
        """Get a specific user share by name.

        Args:
            name: Share name.
        """
        try:
            client = require_client(ctx)
            shares = await client.list_shares()
            for share in shares:
                if share.get("name") == name:
                    return share
            return {"error": f"Share '{name}' not found"}
        except Exception as e:
            handle_client_error(e)
