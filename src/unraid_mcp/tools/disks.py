"""Disk tools (read-only)."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from unraid_mcp.models.disks import Disk
from unraid_mcp.tools._helpers import require_client, unraid_tool


def register_disk_tools(mcp: FastMCP) -> None:
    """Register physical disk tools."""

    @unraid_tool(mcp, tags={"disks"})
    async def unraid_list_disks(ctx: Context) -> list[Disk]:
        """List all physical disks attached to the system, with SMART status and basic info.

        Args:
            ctx: FastMCP request context.

        Returns:
            List of ``Disk`` models, one per attached physical disk.
        """
        client = require_client(ctx)
        return await client.list_disks()

    @unraid_tool(mcp, tags={"disks"})
    async def unraid_get_disk(ctx: Context, disk_id: str) -> Disk:
        """Get detailed info for a specific disk by ID.

        Args:
            ctx: FastMCP request context.
            disk_id: Disk identifier (typically the device serial or Unraid-assigned ID).

        Returns:
            ``Disk`` model for the matching disk.
        """
        client = require_client(ctx)
        return await client.get_disk(disk_id)

    @unraid_tool(mcp, tags={"disks"})
    async def unraid_list_assignable_disks(ctx: Context) -> list[Disk]:
        """List disks eligible for assignment to the array.

        Args:
            ctx: FastMCP request context.

        Returns:
            List of ``Disk`` models for unassigned/assignable disks.
        """
        client = require_client(ctx)
        return await client.list_assignable_disks()
