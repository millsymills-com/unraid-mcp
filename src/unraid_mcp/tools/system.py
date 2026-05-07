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
        """Get system information: OS, CPU, memory, baseboard, and component versions.

        Args:
            ctx: FastMCP request context.

        Returns:
            ``SystemInfo`` model with OS / CPU / memory / baseboard fields.
        """
        try:
            client = require_client(ctx)
            return await client.get_info()
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"system"})
    async def unraid_get_flash(ctx: Context) -> dict[str, Any]:
        """Get Unraid USB flash drive metadata (GUID, vendor, product).

        Args:
            ctx: FastMCP request context.

        Returns:
            Dict of flash metadata keyed by GraphQL field name.
        """
        try:
            client = require_client(ctx)
            return await client.get_flash()
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"system"})
    async def unraid_get_registration(ctx: Context) -> dict[str, Any]:
        """Get Unraid registration: license type, expiration, update entitlement.

        Args:
            ctx: FastMCP request context.

        Returns:
            Dict of registration fields keyed by GraphQL field name.
        """
        try:
            client = require_client(ctx)
            return await client.get_registration()
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"system"})
    async def unraid_get_connect(ctx: Context) -> dict[str, Any]:
        """Get Unraid Connect remote-access configuration.

        Args:
            ctx: FastMCP request context.

        Returns:
            Dict of Unraid Connect configuration fields keyed by GraphQL field name.
        """
        try:
            client = require_client(ctx)
            return await client.get_connect()
        except Exception as e:
            handle_client_error(e)
