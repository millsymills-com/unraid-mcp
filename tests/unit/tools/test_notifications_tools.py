"""Tool tests for the notifications domain."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.models.notifications import Notification


class TestListNotifications:
    async def test_returns_list(self, client_rw):
        client, mock = client_rw
        mock.list_notifications.return_value = [
            Notification(id="n1", title="Parity check complete", importance="normal"),
        ]
        result = await client.call_tool("unraid_list_notifications")
        assert result.structured_content["result"][0]["title"] == "Parity check complete"


class TestWriteNotificationOps:
    async def test_archive_forwards_id(self, client_rw):
        client, mock = client_rw
        mock.archive_notification.return_value = {"archiveNotification": {"id": "n1"}}
        await client.call_tool("unraid_archive_notification", {"notification_id": "n1"})
        mock.archive_notification.assert_awaited_once_with("n1")

    async def test_delete_forwards_id_and_default_type(self, client_rw):
        client, mock = client_rw
        mock.delete_notification.return_value = {"unread": {"total": 0}}
        await client.call_tool("unraid_delete_notification", {"notification_id": "n1"})
        mock.delete_notification.assert_awaited_once_with("n1", notification_type="UNREAD")

    async def test_delete_forwards_explicit_type(self, client_rw):
        client, mock = client_rw
        mock.delete_notification.return_value = {"archive": {"total": 0}}
        await client.call_tool(
            "unraid_delete_notification",
            {"notification_id": "n1", "notification_type": "ARCHIVE"},
        )
        mock.delete_notification.assert_awaited_once_with("n1", notification_type="ARCHIVE")

    async def test_archive_all_invokes_client(self, client_rw):
        client, mock = client_rw
        mock.archive_all_notifications.return_value = {"unread": {"total": 0}}
        await client.call_tool("unraid_archive_all_notifications")
        mock.archive_all_notifications.assert_awaited_once_with(importance=None)

    async def test_archive_all_forwards_importance(self, client_rw):
        client, mock = client_rw
        mock.archive_all_notifications.return_value = {"unread": {"total": 0}}
        await client.call_tool("unraid_archive_all_notifications", {"importance": "WARNING"})
        mock.archive_all_notifications.assert_awaited_once_with(importance="WARNING")

    async def test_delete_hidden_in_readonly(self, client_ro):
        client, _ = client_ro
        with pytest.raises(ToolError, match="Unknown tool"):
            await client.call_tool("unraid_delete_notification", {"notification_id": "n1"})
