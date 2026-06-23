"""MCP tool definitions for the Unraid GraphQL API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = logging.getLogger(__name__)


def register_all_tools(mcp: FastMCP) -> None:
    """Register all Unraid tools on the server."""
    from unraid_mcp.tools.array import register_array_tools
    from unraid_mcp.tools.disks import register_disk_tools
    from unraid_mcp.tools.docker import register_docker_tools
    from unraid_mcp.tools.logs import register_log_tools
    from unraid_mcp.tools.metrics import register_metrics_tools
    from unraid_mcp.tools.notifications import register_notification_tools
    from unraid_mcp.tools.oidc import register_oidc_tools
    from unraid_mcp.tools.parity import register_parity_tools
    from unraid_mcp.tools.plugins import register_plugin_tools
    from unraid_mcp.tools.rclone import register_rclone_tools
    from unraid_mcp.tools.shares import register_share_tools
    from unraid_mcp.tools.system import register_system_tools
    from unraid_mcp.tools.ups import register_ups_tools
    from unraid_mcp.tools.users import register_user_tools
    from unraid_mcp.tools.vms import register_vm_tools

    register_system_tools(mcp)
    register_array_tools(mcp)
    register_parity_tools(mcp)
    register_disk_tools(mcp)
    register_docker_tools(mcp)
    register_vm_tools(mcp)
    register_share_tools(mcp)
    register_user_tools(mcp)
    register_notification_tools(mcp)
    register_metrics_tools(mcp)
    register_ups_tools(mcp)
    register_plugin_tools(mcp)
    register_log_tools(mcp)
    register_oidc_tools(mcp)
    register_rclone_tools(mcp)
    logger.info("Registered all Unraid tools")
