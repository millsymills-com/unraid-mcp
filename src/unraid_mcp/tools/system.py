"""System / info tools (read-only)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unraid_mcp.models.system import SystemInfo
from unraid_mcp.tools._helpers import require_client, tool_error_boundary


def register_system_tools(mcp: FastMCP) -> None:
    """Register system info tools."""

    @mcp.tool(tags={"system"})
    @tool_error_boundary
    async def unraid_get_info(ctx: Context) -> SystemInfo:
        """Get system information: OS, CPU, memory, baseboard, and component versions."""
        client = require_client(ctx)
        return await client.get_info()

    @mcp.tool(tags={"system"})
    @tool_error_boundary
    async def unraid_get_flash(ctx: Context) -> dict[str, Any]:
        """Get Unraid USB flash drive metadata (GUID, vendor, product)."""
        client = require_client(ctx)
        return await client.get_flash()

    @mcp.tool(tags={"system"})
    @tool_error_boundary
    async def unraid_get_registration(ctx: Context) -> dict[str, Any]:
        """Get Unraid registration: license type, expiration, update entitlement."""
        client = require_client(ctx)
        return await client.get_registration()

    @mcp.tool(tags={"system"})
    @tool_error_boundary
    async def unraid_get_connect(ctx: Context) -> dict[str, Any]:
        """Get Unraid Connect remote-access configuration."""
        client = require_client(ctx)
        return await client.get_connect()
