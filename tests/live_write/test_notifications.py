"""Live mutating tests for notification tools.

The archive and delete tests self-seed their own ``mcptest_*``-titled
notification via the ``seed_notification`` fixture and only ever act on
that id, so they never touch arbitrary user-visible notifications on the
live tower. ``test_archive_all`` cannot self-scope (it archives the whole
active list), so it gates: it skips unless every active notification is
``mcptest_*``-titled — the live-write safety net (see ``conftest.py``
header).

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


async def _seeded_in_active(live_mcp_client, seed_notification, title: str) -> str:
    """Seed a notification and wait until it lands in the active list; return its id."""
    nid = (await seed_notification(title))["id"]
    await wait_for_state(
        lambda: _list_notifications(live_mcp_client),
        predicate=lambda lst: nid in {n["id"] for n in lst},
        timeout=5.0,
    )
    return nid


async def test_unraid_archive_notification_removes_from_active_list(live_mcp_client, seed_notification) -> None:
    """Archive an mcptest notification, verify it disappears from the active list."""
    nid = await _seeded_in_active(live_mcp_client, seed_notification, "mcptest-archive")

    await live_mcp_client.call_tool("unraid_archive_notification", {"notification_id": nid})

    after = await wait_for_state(
        lambda: _list_notifications(live_mcp_client),
        predicate=lambda lst: nid not in {n["id"] for n in lst},
        timeout=5.0,
    )
    assert nid not in {n["id"] for n in after}


async def test_unraid_delete_notification_removes_permanently(live_mcp_client, seed_notification) -> None:
    """Delete an mcptest notification, verify the id is gone from any list."""
    nid = await _seeded_in_active(live_mcp_client, seed_notification, "mcptest-delete")

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
