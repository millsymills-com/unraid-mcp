"""UPS tools (read-only)."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from unraid_mcp.models.ups import UPSConfiguration, UPSDevice
from unraid_mcp.tools._helpers import require_client, unraid_tool


def register_ups_tools(mcp: FastMCP) -> None:
    """Register UPS power-device tools."""

    @unraid_tool(mcp, tags={"ups"})
    async def unraid_list_ups_devices(ctx: Context) -> list[UPSDevice]:
        """List all monitored UPS (uninterruptible power supply) devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            List of ``UPSDevice`` models with battery and power readings.
        """
        client = require_client(ctx)
        return await client.list_ups_devices()

    @unraid_tool(mcp, tags={"ups"})
    async def unraid_get_ups_device(ctx: Context, device_id: str) -> UPSDevice:
        """Get a single UPS device by ID.

        Args:
            ctx: FastMCP request context.
            device_id: UPS device identifier (usually the model name).

        Returns:
            ``UPSDevice`` model for the matching device.

        Raises:
            ToolError: when no device matches ``device_id``.
        """
        client = require_client(ctx)
        return await client.get_ups_device(device_id)

    @unraid_tool(mcp, tags={"ups"})
    async def unraid_get_ups_configuration(ctx: Context) -> UPSConfiguration:
        """Get the UPS monitoring service configuration.

        Args:
            ctx: FastMCP request context.

        Returns:
            ``UPSConfiguration`` model (cable type, thresholds, network mode).
        """
        client = require_client(ctx)
        return await client.get_ups_configuration()
