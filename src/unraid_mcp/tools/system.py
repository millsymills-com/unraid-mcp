"""System / info tools (read-only)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unraid_mcp.models.system import SystemInfo
from unraid_mcp.tools._helpers import require_client, unraid_tool


def register_system_tools(mcp: FastMCP) -> None:
    """Register system info tools."""

    @unraid_tool(mcp, tags={"system"})
    async def unraid_get_info(ctx: Context) -> SystemInfo:
        """Get system information: OS, CPU, memory, baseboard, and component versions.

        Args:
            ctx: FastMCP request context.

        Returns:
            ``SystemInfo`` model with OS / CPU / memory / baseboard fields.
        """
        client = require_client(ctx)
        return await client.get_info()

    @unraid_tool(mcp, tags={"system"})
    async def unraid_get_flash(ctx: Context) -> dict[str, Any]:
        """Get Unraid USB flash drive metadata (vendor, product).

        ``guid`` is intentionally not selected — the Unraid resolver
        returns null on trial/unregistered installs and trips a non-null
        violation on the wire (see #52).

        Args:
            ctx: FastMCP request context.

        Returns:
            Dict of flash metadata keyed by GraphQL field name.
        """
        client = require_client(ctx)
        return await client.get_flash()

    @unraid_tool(mcp, tags={"system"})
    async def unraid_get_registration(ctx: Context) -> dict[str, Any]:
        """Get Unraid registration: license type, expiration, update entitlement.

        Args:
            ctx: FastMCP request context.

        Returns:
            Dict of registration fields keyed by GraphQL field name.
        """
        client = require_client(ctx)
        return await client.get_registration()

    @unraid_tool(mcp, tags={"system"})
    async def unraid_get_connect(ctx: Context) -> dict[str, Any]:
        """Get Unraid Connect remote-access configuration.

        Args:
            ctx: FastMCP request context.

        Returns:
            Dict of Unraid Connect configuration fields keyed by GraphQL field name.
        """
        client = require_client(ctx)
        return await client.get_connect()
