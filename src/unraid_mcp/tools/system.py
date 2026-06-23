"""System / info tools (read-only)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unraid_mcp.models.network import Cloud, Network
from unraid_mcp.models.settings import ApiSettings, DisplaySettings, Service
from unraid_mcp.models.system import SystemInfo
from unraid_mcp.models.system_time import SystemTime, TimeZoneOption
from unraid_mcp.models.vars import Vars
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

    @unraid_tool(mcp, tags={"system"})
    async def unraid_get_network(ctx: Context) -> Network:
        """Get the server's network access URLs (LAN / WAN endpoints).

        Args:
            ctx: FastMCP request context.

        Returns:
            ``Network`` model with the list of access URLs.
        """
        client = require_client(ctx)
        return await client.get_network()

    @unraid_tool(mcp, tags={"system"})
    async def unraid_get_cloud(ctx: Context) -> Cloud:
        """Get Unraid Connect cloud health (relay / mini-GraphQL / reachability).

        Returns health indicators only — API-key material is never included.

        Args:
            ctx: FastMCP request context.

        Returns:
            ``Cloud`` model with secret-free health fields.
        """
        client = require_client(ctx)
        return await client.get_cloud()

    @unraid_tool(mcp, tags={"system"})
    async def unraid_list_services(ctx: Context) -> list[Service]:
        """List background services and their online/uptime status.

        Args:
            ctx: FastMCP request context.

        Returns:
            List of ``Service`` models.
        """
        client = require_client(ctx)
        return await client.list_services()

    @unraid_tool(mcp, tags={"system"})
    async def unraid_get_display_settings(ctx: Context) -> DisplaySettings:
        """Get the UI display settings (theme, units, thresholds, case image URL).

        The large base64-encoded case image is intentionally omitted.

        Args:
            ctx: FastMCP request context.

        Returns:
            ``DisplaySettings`` model.
        """
        client = require_client(ctx)
        return await client.get_display_settings()

    @unraid_tool(mcp, tags={"system"})
    async def unraid_get_api_settings(ctx: Context) -> ApiSettings:
        """Get the Unraid API settings (``settings.api`` branch).

        Args:
            ctx: FastMCP request context.

        Returns:
            ``ApiSettings`` model (version, extra origins, sandbox, plugins).
        """
        client = require_client(ctx)
        return await client.get_api_settings()

    @unraid_tool(mcp, tags={"system"})
    async def unraid_get_system_time(ctx: Context) -> SystemTime:
        """Get the current server time configuration (time, zone, NTP).

        Args:
            ctx: FastMCP request context.

        Returns:
            ``SystemTime`` model.
        """
        client = require_client(ctx)
        return await client.get_system_time()

    @unraid_tool(mcp, tags={"system"})
    async def unraid_list_timezone_options(ctx: Context) -> list[TimeZoneOption]:
        """List available IANA timezone options (value + display label).

        Args:
            ctx: FastMCP request context.

        Returns:
            List of ``TimeZoneOption`` models.
        """
        client = require_client(ctx)
        return await client.list_timezone_options()

    @unraid_tool(mcp, tags={"system"})
    async def unraid_get_vars(ctx: Context) -> Vars:
        """Get a curated, secret-free subset of Unraid system variables.

        Covers version, identity, share counts, array/filesystem state, and
        network/port settings. The session ``csrfToken`` is never included.

        Args:
            ctx: FastMCP request context.

        Returns:
            ``Vars`` model with the curated subset.
        """
        client = require_client(ctx)
        return await client.get_vars()
