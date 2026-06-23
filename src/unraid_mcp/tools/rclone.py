"""Rclone tools (read-only)."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from unraid_mcp.models.rclone import RCloneConfig
from unraid_mcp.tools._helpers import require_client, unraid_tool


def register_rclone_tools(mcp: FastMCP) -> None:
    """Register rclone backup-configuration tools."""

    @unraid_tool(mcp, tags={"rclone"})
    async def unraid_get_rclone_config(ctx: Context) -> RCloneConfig:
        """Get the rclone backup configuration (configured remotes and drivers).

        Credential-bearing JSON (remote ``parameters`` / ``config``) is redacted
        — only remote names/types and available driver names are returned.

        Args:
            ctx: FastMCP request context.

        Returns:
            ``RCloneConfig`` model with ``remotes`` and ``drives``.
        """
        client = require_client(ctx)
        return await client.get_rclone_config()
