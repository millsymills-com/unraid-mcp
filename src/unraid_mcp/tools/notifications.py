"""Notification tools (1 read + 3 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unraid_mcp.models.notifications import Notification
from unraid_mcp.tools._helpers import require_client, require_readwrite, tool_error_boundary


def register_notification_tools(mcp: FastMCP) -> None:
    """Register notification tools."""

    @mcp.tool(tags={"notifications"})
    @tool_error_boundary
    async def unraid_list_notifications(ctx: Context) -> list[Notification]:
        """List active notifications (id, type, title, importance, timestamp)."""
        client = require_client(ctx)
        return await client.list_notifications()

    @mcp.tool(tags={"write", "notifications"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_error_boundary
    async def unraid_archive_notification(ctx: Context, notification_id: str) -> dict[str, Any]:
        """Archive a notification by ID (move out of the active list).

        Args:
            notification_id: Notification ID.
        """
        client = require_readwrite(ctx, "archive notification")
        return await client.archive_notification(notification_id)

    @mcp.tool(tags={"write", "notifications"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_error_boundary
    async def unraid_delete_notification(ctx: Context, notification_id: str) -> dict[str, Any]:
        """Permanently delete a notification by ID.

        Args:
            notification_id: Notification ID.
        """
        client = require_readwrite(ctx, "delete notification")
        return await client.delete_notification(notification_id)

    @mcp.tool(tags={"write", "notifications"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_error_boundary
    async def unraid_archive_all_notifications(ctx: Context) -> dict[str, Any]:
        """Archive all active notifications."""
        client = require_readwrite(ctx, "archive all notifications")
        return await client.archive_all_notifications()
