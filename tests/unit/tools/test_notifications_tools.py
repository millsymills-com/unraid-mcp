"""Tool tests for the notifications domain."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.models.notifications import Notification


def _enum_values(schema: dict) -> set[str]:
    """Extract enum values from a JSON-Schema property (handles direct enum or anyOf)."""
    if "enum" in schema:
        return set(schema["enum"])
    for branch in schema.get("anyOf", []):
        if "enum" in branch:
            return set(branch["enum"])
    raise AssertionError(f"no enum constraint found in {schema!r}")


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
        mock.archive_notification.return_value = {
            "archiveNotification": {
                "unread": {"total": 0, "info": 0, "warning": 0, "alert": 0},
                "archive": {"total": 1, "info": 1, "warning": 0, "alert": 0},
            },
        }
        await client.call_tool("unraid_archive_notification", {"notification_id": "n1"})
        mock.archive_notification.assert_awaited_once_with("n1")

    async def test_delete_defaults_type_to_unread(self, client_rw):
        # Drift #61: ``deleteNotification`` requires a ``type`` argument
        # and the tool defaults it to ``UNREAD``.
        client, mock = client_rw
        mock.delete_notification.return_value = {
            "deleteNotification": {
                "unread": {"total": 0, "info": 0, "warning": 0, "alert": 0},
                "archive": {"total": 0, "info": 0, "warning": 0, "alert": 0},
            },
        }
        await client.call_tool("unraid_delete_notification", {"notification_id": "n1"})
        mock.delete_notification.assert_awaited_once_with("n1", notification_type="UNREAD")

    async def test_delete_forwards_explicit_type(self, client_rw):
        client, mock = client_rw
        mock.delete_notification.return_value = {
            "deleteNotification": {
                "unread": {"total": 0, "info": 0, "warning": 0, "alert": 0},
                "archive": {"total": 0, "info": 0, "warning": 0, "alert": 0},
            },
        }
        await client.call_tool(
            "unraid_delete_notification",
            {"notification_id": "n1", "notification_type": "ARCHIVE"},
        )
        mock.delete_notification.assert_awaited_once_with("n1", notification_type="ARCHIVE")

    async def test_archive_all_invokes_client_with_no_importance(self, client_rw):
        # Drift #61: ``archiveAll`` accepts an optional importance
        # filter; the tool passes ``None`` when callers omit it.
        client, mock = client_rw
        mock.archive_all_notifications.return_value = {
            "archiveAll": {
                "unread": {"total": 0, "info": 0, "warning": 0, "alert": 0},
                "archive": {"total": 5, "info": 3, "warning": 1, "alert": 1},
            },
        }
        await client.call_tool("unraid_archive_all_notifications")
        mock.archive_all_notifications.assert_awaited_once_with(importance=None)

    async def test_archive_all_forwards_importance_filter(self, client_rw):
        client, mock = client_rw
        mock.archive_all_notifications.return_value = {
            "archiveAll": {
                "unread": {"total": 0, "info": 0, "warning": 0, "alert": 0},
                "archive": {"total": 2, "info": 0, "warning": 2, "alert": 0},
            },
        }
        await client.call_tool("unraid_archive_all_notifications", {"importance": "WARNING"})
        mock.archive_all_notifications.assert_awaited_once_with(importance="WARNING")

    async def test_delete_hidden_in_readonly(self, client_ro):
        client, _ = client_ro
        with pytest.raises(ToolError, match="Unknown tool"):
            await client.call_tool("unraid_delete_notification", {"notification_id": "n1"})


class TestNotificationLiteralSchemas:
    """FastMCP renders ``Literal[...]`` as a JSON-Schema ``enum`` (#165).

    Schema-level enums let the MCP runtime reject invalid inputs at boot
    and dispatch — bare ``str`` would silently forward any string to the
    Unraid GraphQL API.
    """

    async def test_list_notifications_type_is_enum_constrained(self, client_rw):
        client, _ = client_rw
        tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "unraid_list_notifications")
        prop = tool.inputSchema["properties"]["notification_type"]
        assert _enum_values(prop) == {"UNREAD", "ARCHIVE"}

    async def test_delete_notification_type_is_enum_constrained(self, client_rw):
        client, _ = client_rw
        tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "unraid_delete_notification")
        prop = tool.inputSchema["properties"]["notification_type"]
        assert _enum_values(prop) == {"UNREAD", "ARCHIVE"}

    async def test_archive_all_importance_is_enum_constrained(self, client_rw):
        client, _ = client_rw
        tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "unraid_archive_all_notifications")
        prop = tool.inputSchema["properties"]["importance"]
        assert _enum_values(prop) == {"INFO", "WARNING", "ALERT"}

    async def test_delete_notification_rejects_invalid_type(self, client_rw):
        client, _ = client_rw
        with pytest.raises(ToolError):
            await client.call_tool(
                "unraid_delete_notification",
                {"notification_id": "n1", "notification_type": "BOGUS"},
            )

    async def test_archive_all_rejects_invalid_importance(self, client_rw):
        client, _ = client_rw
        with pytest.raises(ToolError):
            await client.call_tool(
                "unraid_archive_all_notifications",
                {"importance": "CRITICAL"},
            )

    @pytest.mark.parametrize("importance", ["INFO", "WARNING", "ALERT"])
    async def test_archive_all_accepts_every_literal_value(self, client_rw, importance):
        client, mock = client_rw
        mock.archive_all_notifications.return_value = {
            "archiveAll": {
                "unread": {"total": 0, "info": 0, "warning": 0, "alert": 0},
                "archive": {"total": 1, "info": 0, "warning": 0, "alert": 0},
            },
        }
        await client.call_tool("unraid_archive_all_notifications", {"importance": importance})
        mock.archive_all_notifications.assert_awaited_once_with(importance=importance)
