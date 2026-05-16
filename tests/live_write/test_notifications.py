"""Live mutating tests for notification tools."""

from __future__ import annotations

import pytest

from tests.live_write.conftest import wait_for_state

pytestmark = pytest.mark.live_write


async def _list_notifications(live_mcp_client) -> list[dict]:
    res = await live_mcp_client.call_tool("unraid_list_notifications", {})
    raw = res.structured_content
    return raw if isinstance(raw, list) else raw.get("result", [])


async def test_archive_notification_removes_from_active_list(live_mcp_client) -> None:
    """Archive a notification, verify it disappears from the active list."""
    active = await _list_notifications(live_mcp_client)
    if not active:
        pytest.skip("no active notifications to archive")
    target = active[0]
    nid = target["id"]

    await live_mcp_client.call_tool("unraid_archive_notification", {"notification_id": nid})

    after = await wait_for_state(
        lambda: _list_notifications(live_mcp_client),
        predicate=lambda lst: nid not in {n["id"] for n in lst},
        timeout=5.0,
    )
    assert nid not in {n["id"] for n in after}


async def test_delete_notification_removes_permanently(live_mcp_client) -> None:
    """Delete a notification, verify the id is gone from any list."""
    active = await _list_notifications(live_mcp_client)
    if not active:
        pytest.skip("no notifications to delete")
    target = active[0]
    nid = target["id"]

    await live_mcp_client.call_tool("unraid_delete_notification", {"notification_id": nid})

    after = await _list_notifications(live_mcp_client)
    assert nid not in {n["id"] for n in after}


async def test_archive_all_notifications_clears_active(live_mcp_client) -> None:
    """archive_all moves every active notification out of the list."""
    active = await _list_notifications(live_mcp_client)
    if not active:
        pytest.skip("no active notifications to archive_all")

    await live_mcp_client.call_tool("unraid_archive_all_notifications", {})

    after = await wait_for_state(
        lambda: _list_notifications(live_mcp_client),
        predicate=lambda lst: len(lst) == 0,
        timeout=5.0,
    )
    assert after == []
