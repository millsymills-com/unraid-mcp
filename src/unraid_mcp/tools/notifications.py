"""Notification tools (1 read + 3 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unraid_mcp.errors import handle_client_error
from unraid_mcp.models.notifications import Notification
from unraid_mcp.tools._helpers import require_client, require_readwrite


def register_notification_tools(mcp: FastMCP) -> None:
    """Register notification tools."""

    @mcp.tool(tags={"notifications"})
    async def unraid_list_notifications(ctx: Context) -> list[Notification]:
        """List active notifications (id, type, title, importance, timestamp)."""
        try:
            client = require_client(ctx)
            return await client.list_notifications()
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "notifications"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unraid_archive_notification(ctx: Context, notification_id: str) -> dict[str, Any]:
        """Archive a notification by ID (move out of the active list).

        Args:
            notification_id: Notification ID.
        """
        try:
            client = require_readwrite(ctx, "archive notification")
            return await client.archive_notification(notification_id)
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "notifications"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    async def unraid_delete_notification(
        ctx: Context,
        notification_id: str,
        notification_type: str = "UNREAD",
    ) -> dict[str, Any]:
        """Permanently delete a notification.

        Args:
            notification_id: Notification ID.
            notification_type: Which bin the notification lives in —
                ``UNREAD`` (default) or ``ARCHIVE``.
        """
        try:
            client = require_readwrite(ctx, "delete notification")
            return await client.delete_notification(notification_id, notification_type=notification_type)
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "notifications"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    async def unraid_archive_all_notifications(
        ctx: Context,
        importance: str | None = None,
    ) -> dict[str, Any]:
        """Archive all active notifications.

        Args:
            importance: Optional filter — only archive notifications at or
                above this importance (``INFO``, ``WARNING``, or ``ALERT``).
                When ``None``, archives all.
        """
        try:
            client = require_readwrite(ctx, "archive all notifications")
            return await client.archive_all_notifications(importance=importance)
        except Exception as e:
            handle_client_error(e)
