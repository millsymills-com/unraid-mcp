"""Live mutating tests for parity check tools.

Sequence: start -> pause -> resume -> cancel. Finalizer always cancels
to avoid leaving a parity check running on the live array.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from tests.live_write.conftest import wait_for_state

pytestmark = pytest.mark.live_write


async def _array_state(live_mcp_client) -> dict:
    res = await live_mcp_client.call_tool("unraid_get_array", {})
    return res.structured_content


async def test_start_pause_resume_cancel_parity_lifecycle(live_mcp_client, request: pytest.FixtureRequest) -> None:
    """End-to-end parity lifecycle. Single test (not split) so cleanup is atomic."""
    initial = await _array_state(live_mcp_client)
    if (initial.get("state") or "").upper() != "STARTED":
        pytest.skip(f"array not STARTED (state={initial.get('state')}); cannot start parity")

    async def _cancel() -> None:
        with contextlib.suppress(Exception):
            await live_mcp_client.call_tool("unraid_cancel_parity_check", {})

    def _sync_cancel() -> None:
        with contextlib.suppress(Exception):
            asyncio.run(_cancel())

    request.addfinalizer(_sync_cancel)

    await live_mcp_client.call_tool("unraid_start_parity_check", {"correct": False})
    await live_mcp_client.call_tool("unraid_pause_parity_check", {})
    await live_mcp_client.call_tool("unraid_resume_parity_check", {})
    await live_mcp_client.call_tool("unraid_cancel_parity_check", {})
    await wait_for_state(
        lambda: _array_state(live_mcp_client),
        predicate=lambda _s: True,
        timeout=5.0,
    )
