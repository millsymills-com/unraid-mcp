"""Array tools (1 read + 2 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unraid_mcp.errors import handle_client_error
from unraid_mcp.models.array import ArrayState
from unraid_mcp.tools._helpers import require_client, require_readwrite


def register_array_tools(mcp: FastMCP) -> None:
    """Register array tools."""

    @mcp.tool(tags={"array"})
    async def unraid_get_array(ctx: Context) -> ArrayState:
        """Get array status, capacity, parity disks, data disks, and cache disks."""
        try:
            client = require_client(ctx)
            return await client.get_array()
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "array"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unraid_start_array(ctx: Context) -> dict[str, Any]:
        """Start the Unraid array."""
        try:
            client = require_readwrite(ctx, "start array")
            return await client.start_array()
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "array"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    async def unraid_stop_array(ctx: Context) -> dict[str, Any]:
        """Stop the Unraid array (will unmount shares and stop Docker/VMs)."""
        try:
            client = require_readwrite(ctx, "stop array")
            return await client.stop_array()
        except Exception as e:
            handle_client_error(e)
