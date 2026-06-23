"""Plugin tools (read-only)."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from unraid_mcp.models.plugins import Plugin, PluginInstallOperation
from unraid_mcp.tools._helpers import require_client, unraid_tool


def register_plugin_tools(mcp: FastMCP) -> None:
    """Register plugin inventory and install-operation tools."""

    @unraid_tool(mcp, tags={"plugins"})
    async def unraid_list_plugins(ctx: Context) -> list[Plugin]:
        """List all installed plugins with their metadata.

        Args:
            ctx: FastMCP request context.

        Returns:
            List of ``Plugin`` models (name, version, module flags).
        """
        client = require_client(ctx)
        return await client.list_plugins()

    @unraid_tool(mcp, tags={"plugins"})
    async def unraid_list_installed_plugins(ctx: Context) -> list[str]:
        """List installed Unraid OS plugins by ``.plg`` filename.

        Args:
            ctx: FastMCP request context.

        Returns:
            List of ``.plg`` filenames.
        """
        client = require_client(ctx)
        return await client.list_installed_unraid_plugins()

    @unraid_tool(mcp, tags={"plugins"})
    async def unraid_list_plugin_install_operations(ctx: Context) -> list[PluginInstallOperation]:
        """List all tracked plugin-install operations.

        Args:
            ctx: FastMCP request context.

        Returns:
            List of ``PluginInstallOperation`` models with status and output.
        """
        client = require_client(ctx)
        return await client.list_plugin_install_operations()

    @unraid_tool(mcp, tags={"plugins"})
    async def unraid_get_plugin_install_operation(ctx: Context, operation_id: str) -> PluginInstallOperation:
        """Get a single plugin-install operation by ID.

        Args:
            ctx: FastMCP request context.
            operation_id: The install-operation identifier.

        Returns:
            ``PluginInstallOperation`` model for the matching operation.

        Raises:
            ToolError: when no operation matches ``operation_id``.
        """
        client = require_client(ctx)
        return await client.get_plugin_install_operation(operation_id)
