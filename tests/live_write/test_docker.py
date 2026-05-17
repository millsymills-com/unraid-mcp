"""Live mutating tests for Docker container tools.

Uses the discovered mcptest-* container. Tests stop/start/pause/unpause/restart
and always restore the container to its original state in a finalizer.

Test function names intentionally embed the underlying tool name so the
manifest <-> live-test parity meta-test can match each tool to a test ID.
"""

from __future__ import annotations

import pytest

from tests.live_write.conftest import _assert_mcptest, run_cleanup, wait_for_state

pytestmark = pytest.mark.live_write


async def _container_state(live_mcp_client, container_id: str) -> str:
    res = await live_mcp_client.call_tool("unraid_get_container", {"container_id": container_id})
    return (res.structured_content or {}).get("state", "")


async def _stop_start_cycle(live_mcp_client, mcptest_container, request: pytest.FixtureRequest) -> None:
    name = (mcptest_container.get("names") or ["?"])[0].lstrip("/")
    _assert_mcptest(name)
    cid = mcptest_container["id"]

    initial = await _container_state(live_mcp_client, cid)

    def _restore() -> None:
        tool = "unraid_start_container" if initial == "running" else "unraid_stop_container"
        run_cleanup(
            f"{tool}({cid}) restore for {name}",
            lambda: live_mcp_client.call_tool(tool, {"container_id": cid}),
        )

    request.addfinalizer(_restore)

    await live_mcp_client.call_tool("unraid_stop_container", {"container_id": cid})
    state = await wait_for_state(
        lambda: _container_state(live_mcp_client, cid),
        predicate=lambda s: s in {"exited", "stopped", "dead", ""},
    )
    assert state in {"exited", "stopped", "dead", ""}, f"unexpected state {state!r}"

    await live_mcp_client.call_tool("unraid_start_container", {"container_id": cid})
    state = await wait_for_state(
        lambda: _container_state(live_mcp_client, cid),
        predicate=lambda s: s == "running",
    )
    assert state == "running"


async def test_unraid_stop_container_then_unraid_start_container(
    live_mcp_client, mcptest_container, request: pytest.FixtureRequest
) -> None:
    """Stop a running mcptest container, verify state, start it back, verify."""
    await _stop_start_cycle(live_mcp_client, mcptest_container, request)


async def _pause_unpause_cycle(live_mcp_client, mcptest_container, request: pytest.FixtureRequest) -> None:
    name = (mcptest_container.get("names") or ["?"])[0].lstrip("/")
    _assert_mcptest(name)
    cid = mcptest_container["id"]

    if (await _container_state(live_mcp_client, cid)) != "running":
        pytest.skip(f"{name} is not running; can't pause")

    def _unpause() -> None:
        run_cleanup(
            f"unraid_unpause_container({cid}) for {name}",
            lambda: live_mcp_client.call_tool("unraid_unpause_container", {"container_id": cid}),
        )

    request.addfinalizer(_unpause)

    await live_mcp_client.call_tool("unraid_pause_container", {"container_id": cid})
    state = await wait_for_state(
        lambda: _container_state(live_mcp_client, cid),
        predicate=lambda s: s == "paused",
    )
    assert state == "paused"

    await live_mcp_client.call_tool("unraid_unpause_container", {"container_id": cid})
    state = await wait_for_state(
        lambda: _container_state(live_mcp_client, cid),
        predicate=lambda s: s == "running",
    )
    assert state == "running"


async def test_unraid_pause_container_then_unraid_unpause_container(
    live_mcp_client, mcptest_container, request: pytest.FixtureRequest
) -> None:
    """Pause + unpause a running mcptest container."""
    await _pause_unpause_cycle(live_mcp_client, mcptest_container, request)


async def test_unraid_restart_container(live_mcp_client, mcptest_container) -> None:
    """Restart returns the container to running state; covers the restart wrapper."""
    name = (mcptest_container.get("names") or ["?"])[0].lstrip("/")
    _assert_mcptest(name)
    cid = mcptest_container["id"]

    await live_mcp_client.call_tool("unraid_restart_container", {"container_id": cid})
    state = await wait_for_state(
        lambda: _container_state(live_mcp_client, cid),
        predicate=lambda s: s == "running",
        timeout=15.0,
    )
    assert state == "running"
