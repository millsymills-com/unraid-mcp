"""Disk tools (read-only)."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from unraid_mcp.errors import UnraidNotFoundError, handle_client_error
from unraid_mcp.models.disks import Disk
from unraid_mcp.tools._helpers import require_client


def register_disk_tools(mcp: FastMCP) -> None:
    """Register physical disk tools."""

    @mcp.tool(tags={"disks"})
    async def unraid_list_disks(ctx: Context) -> list[Disk]:
        """List all physical disks attached to the system, with SMART status and basic info."""
        try:
            client = require_client(ctx)
            return await client.list_disks()
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"disks"})
    async def unraid_get_disk(ctx: Context, disk_id: str) -> Disk:
        """Get detailed info for a specific disk by ID.

        Args:
            disk_id: Disk identifier (typically the device serial or Unraid-assigned ID).
        """
        try:
            client = require_client(ctx)
            disks = await client.list_disks()
            for disk in disks:
                if disk_id in (disk.id, disk.name):
                    return disk
            raise UnraidNotFoundError(f"Disk with id '{disk_id}' not found")
        except Exception as e:
            handle_client_error(e)
