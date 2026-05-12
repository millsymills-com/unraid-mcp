"""Notification tools (1 read + 3 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unraid_mcp.models.notifications import Notification, NotificationImportance, NotificationType
from unraid_mcp.tools._helpers import require_client, require_readwrite, unraid_tool


def register_notification_tools(mcp: FastMCP) -> None:
    """Register notification tools."""

    @unraid_tool(mcp, tags={"notifications"})
    async def unraid_list_notifications(
        ctx: Context,
        notification_type: NotificationType = "UNREAD",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """List notifications (id, type, title, importance, timestamp).

        Args:
            ctx: FastMCP request context.
            notification_type: Which bin to list — ``UNREAD`` (default) or ``ARCHIVE``.
                The Unraid API 4.32+ schema requires this filter.
            limit: Max entries to return (default 50).
            offset: Pagination offset (default 0).

        Returns:
            List of ``Notification`` models, one per entry in the selected bin.
        """
        client = require_client(ctx)
        return await client.list_notifications(
            notification_type=notification_type,
            limit=limit,
            offset=offset,
        )

    @unraid_tool(mcp, tags={"write", "notifications"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unraid_archive_notification(ctx: Context, notification_id: str) -> dict[str, Any]:
        """Archive a notification by ID (move out of the active list).

        Args:
            ctx: FastMCP request context.
            notification_id: Notification ID.

        Returns:
            Raw GraphQL mutation response payload.
        """
        client = require_readwrite(ctx, "archive notification")
        return await client.archive_notification(notification_id)

    @unraid_tool(mcp, tags={"write", "notifications"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    async def unraid_delete_notification(
        ctx: Context,
        notification_id: str,
        notification_type: NotificationType = "UNREAD",
    ) -> dict[str, Any]:
        """Permanently delete a notification by ID.

        Args:
            ctx: FastMCP request context.
            notification_id: Notification ID.
            notification_type: Which bin holds the entry — ``UNREAD``
                (default) or ``ARCHIVE``. Required by the Unraid API
                4.32+ schema so the server can decrement the correct
                counter (#61).

        Returns:
            Raw GraphQL mutation response payload.
        """
        client = require_readwrite(ctx, "delete notification")
        return await client.delete_notification(notification_id, notification_type=notification_type)

    @unraid_tool(mcp, tags={"write", "notifications"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    async def unraid_archive_all_notifications(
        ctx: Context,
        importance: NotificationImportance | None = None,
    ) -> dict[str, Any]:
        """Archive all active notifications.

        Args:
            ctx: FastMCP request context.
            importance: Optional ``NotificationImportance`` filter
                (``INFO`` / ``WARNING`` / ``ALERT``). When omitted all
                active notifications are archived (#61).

        Returns:
            Raw GraphQL mutation response payload.
        """
        client = require_readwrite(ctx, "archive all notifications")
        return await client.archive_all_notifications(importance=importance)
