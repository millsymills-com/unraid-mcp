"""Live mutating tests for notification tools.

All three tests gate on a ``mcptest_*``-titled notification existing in
the active list. Without this guard the tests would archive or delete
arbitrary user-visible notifications on the live tower (alerts, parity
warnings, etc.) — the third layer of the live-write safety net (see
``conftest.py`` header).

Test function names intentionally embed the underlying tool name so the
manifest <-> live-test parity meta-test can match each tool to a test ID.
"""

from __future__ import annotations

import pytest

from tests.live_write.conftest import wait_for_state

pytestmark = pytest.mark.live_write

_MCPTEST_PREFIX = "mcptest"


async def _list_notifications(live_mcp_client) -> list[dict]:
    res = await live_mcp_client.call_tool("unraid_list_notifications", {})
    raw = res.structured_content
    return raw if isinstance(raw, list) else raw.get("result", [])


def _mcptest_only(notifications: list[dict]) -> list[dict]:
    return [n for n in notifications if str(n.get("title", "")).lower().startswith(_MCPTEST_PREFIX)]


async def test_unraid_archive_notification_removes_from_active_list(live_mcp_client) -> None:
    """Archive an mcptest notification, verify it disappears from the active list."""
    mcptest = _mcptest_only(await _list_notifications(live_mcp_client))
    if not mcptest:
        pytest.skip(
            "no mcptest_*-titled active notification; create one on the tower "
            "(Notifications → Add, title=mcptest-archive) to enable this test"
        )
    nid = mcptest[0]["id"]

    await live_mcp_client.call_tool("unraid_archive_notification", {"notification_id": nid})

    after = await wait_for_state(
        lambda: _list_notifications(live_mcp_client),
        predicate=lambda lst: nid not in {n["id"] for n in lst},
        timeout=5.0,
    )
    assert nid not in {n["id"] for n in after}


async def test_unraid_delete_notification_removes_permanently(live_mcp_client) -> None:
    """Delete an mcptest notification, verify the id is gone from any list."""
    mcptest = _mcptest_only(await _list_notifications(live_mcp_client))
    if not mcptest:
        pytest.skip(
            "no mcptest_*-titled active notification; create one on the tower "
            "(Notifications → Add, title=mcptest-delete) to enable this test"
        )
    nid = mcptest[0]["id"]

    await live_mcp_client.call_tool("unraid_delete_notification", {"notification_id": nid})

    after = await _list_notifications(live_mcp_client)
    assert nid not in {n["id"] for n in after}


async def test_unraid_archive_all_notifications_clears_active(live_mcp_client) -> None:
    """archive_all archives every active notification — only safe when all are mcptest_*."""
    active = await _list_notifications(live_mcp_client)
    if not active:
        pytest.skip("no active notifications to archive_all")
    non_mcptest = [n for n in active if not str(n.get("title", "")).lower().startswith(_MCPTEST_PREFIX)]
    if non_mcptest:
        titles = ", ".join(repr(n.get("title")) for n in non_mcptest[:3])
        pytest.skip(
            f"refusing to run archive_all: active list contains non-mcptest notifications ({titles}...). "
            "Resolve them via the WebGUI or rename to start with `mcptest`."
        )

    await live_mcp_client.call_tool("unraid_archive_all_notifications", {})

    after = await wait_for_state(
        lambda: _list_notifications(live_mcp_client),
        predicate=lambda lst: len(lst) == 0,
        timeout=5.0,
    )
    assert after == []
