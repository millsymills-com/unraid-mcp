"""Array tools (1 read + 2 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unraid_mcp.models.array import ArrayState
from unraid_mcp.tools._helpers import require_client, require_readwrite, tool_error_boundary


def register_array_tools(mcp: FastMCP) -> None:
    """Register array tools."""

    @mcp.tool(tags={"array"})
    @tool_error_boundary
    async def unraid_get_array(ctx: Context) -> ArrayState:
        """Get array status, capacity, parity disks, data disks, and cache disks."""
        client = require_client(ctx)
        return await client.get_array()

    @mcp.tool(tags={"write", "array"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_error_boundary
    async def unraid_start_array(ctx: Context) -> dict[str, Any]:
        """Start the Unraid array."""
        client = require_readwrite(ctx, "start array")
        return await client.start_array()

    @mcp.tool(tags={"write", "array"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_error_boundary
    async def unraid_stop_array(ctx: Context) -> dict[str, Any]:
        """Stop the Unraid array (will unmount shares and stop Docker/VMs)."""
        client = require_readwrite(ctx, "stop array")
        return await client.stop_array()
