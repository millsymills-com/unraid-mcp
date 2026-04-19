"""System / info tools (read-only)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unraid_mcp.errors import handle_client_error
from unraid_mcp.models.system import SystemInfo
from unraid_mcp.tools._helpers import require_client


def register_system_tools(mcp: FastMCP) -> None:
    """Register system info tools."""

    @mcp.tool(tags={"system"})
    async def unraid_get_info(ctx: Context) -> SystemInfo:
        """Get system information: OS, CPU, memory, baseboard, and component versions."""
        try:
            client = require_client(ctx)
            return await client.get_info()
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"system"})
    async def unraid_get_flash(ctx: Context) -> dict[str, Any]:
        """Get Unraid USB flash drive metadata (GUID, vendor, product)."""
        try:
            client = require_client(ctx)
            return await client.get_flash()
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"system"})
    async def unraid_get_registration(ctx: Context) -> dict[str, Any]:
        """Get Unraid registration: license type, expiration, update entitlement."""
        try:
            client = require_client(ctx)
            return await client.get_registration()
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"system"})
    async def unraid_get_connect(ctx: Context) -> dict[str, Any]:
        """Get Unraid Connect remote-access configuration."""
        try:
            client = require_client(ctx)
            return await client.get_connect()
        except Exception as e:
            handle_client_error(e)
