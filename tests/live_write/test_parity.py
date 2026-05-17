"""Live mutating tests for parity check tools.

Sequence: start -> pause -> resume -> cancel. Finalizer always cancels
to avoid leaving a parity check running on the live array.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from tests.live_write.conftest import run_cleanup, wait_for_state
from unraid_mcp.config import UnraidConfig, UnraidMode
from unraid_mcp.server import create_server

pytestmark = pytest.mark.live_write


async def _array_state(live_mcp_client) -> dict:
    res = await live_mcp_client.call_tool("unraid_get_array", {})
    return res.structured_content


async def test_unraid_start_parity_check_unraid_pause_parity_check_unraid_resume_parity_check_unraid_cancel_parity_check_lifecycle(  # noqa: E501
    live_mcp_client, request: pytest.FixtureRequest
) -> None:
    """End-to-end parity lifecycle. Single test (not split) so cleanup is atomic.

    Function name embeds every tool name exercised so the manifest <-> live-test
    parity meta-test can match each via substring lookup against collected IDs.
    """
    initial = await _array_state(live_mcp_client)
    if (initial.get("state") or "").upper() != "STARTED":
        pytest.skip(f"array not STARTED (state={initial.get('state')}); cannot start parity")

    def _sync_cancel() -> None:
        """Safety-net cancel via a fresh client + fresh loop.

        We don't reuse ``live_mcp_client`` here because finalizers run
        after the test's event loop is torn down — sharing the bound
        httpx async client across loops hangs on close-wait sockets.
        """

        async def _do_cancel() -> None:
            cfg = UnraidConfig(unraid_mode=UnraidMode.READWRITE)
            server = create_server(cfg)
            async with Client(server) as fresh:
                await fresh.call_tool("unraid_cancel_parity_check", {})

        run_cleanup("safety-net unraid_cancel_parity_check", _do_cancel)

    request.addfinalizer(_sync_cancel)

    await live_mcp_client.call_tool("unraid_start_parity_check", {"correct": False})
    await live_mcp_client.call_tool("unraid_pause_parity_check", {})
    await live_mcp_client.call_tool("unraid_resume_parity_check", {})
    await live_mcp_client.call_tool("unraid_cancel_parity_check", {})

    def _parity_idle(state: dict) -> bool:
        parity = state.get("parity") or {}
        running = parity.get("running") or parity.get("active") or parity.get("inProgress")
        return not bool(running)

    await wait_for_state(
        lambda: _array_state(live_mcp_client),
        predicate=_parity_idle,
        timeout=30.0,
    )
