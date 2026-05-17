"""Live mutating tests for VM tools.

Uses the discovered mcptest-* VM. Covers start/stop/pause/resume/reboot.
Skips force_stop_vm — that's waived in the coverage manifest as disruptive.

Test function names intentionally embed the underlying tool name so the
manifest <-> live-test parity meta-test can match each tool to a test ID.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from tests.live_write.conftest import _assert_mcptest, wait_for_state

pytestmark = pytest.mark.live_write


async def _vm_state(live_mcp_client, vm_id: str) -> str:
    res = await live_mcp_client.call_tool("unraid_list_vms", {})
    payload = res.structured_content or {}
    for d in payload.get("domain") or []:
        if d.get("id") == vm_id:
            return d.get("state", "")
    return "missing"


async def test_unraid_start_vm_then_unraid_stop_vm(live_mcp_client, mcptest_vm, request: pytest.FixtureRequest) -> None:
    """Start an mcptest VM, verify state, stop it, verify."""
    _assert_mcptest(mcptest_vm["name"])
    vm_id = mcptest_vm["id"]

    def _stop() -> None:
        with contextlib.suppress(Exception):
            asyncio.run(live_mcp_client.call_tool("unraid_stop_vm", {"vm_id": vm_id}))

    request.addfinalizer(_stop)

    await live_mcp_client.call_tool("unraid_start_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() in {"running", "started"},
        timeout=20.0,
    )

    await live_mcp_client.call_tool("unraid_stop_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() in {"shutoff", "stopped", "shut off"},
        timeout=30.0,
    )


async def test_unraid_pause_vm_then_unraid_resume_vm(
    live_mcp_client, mcptest_vm, request: pytest.FixtureRequest
) -> None:
    """Pause + resume a running mcptest VM."""
    _assert_mcptest(mcptest_vm["name"])
    vm_id = mcptest_vm["id"]

    if (await _vm_state(live_mcp_client, vm_id)).lower() not in {"running", "started"}:
        pytest.skip(f"VM not running; can't pause (state={await _vm_state(live_mcp_client, vm_id)})")

    def _resume() -> None:
        with contextlib.suppress(Exception):
            asyncio.run(live_mcp_client.call_tool("unraid_resume_vm", {"vm_id": vm_id}))

    request.addfinalizer(_resume)

    await live_mcp_client.call_tool("unraid_pause_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() == "paused",
        timeout=15.0,
    )

    await live_mcp_client.call_tool("unraid_resume_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() in {"running", "started"},
        timeout=15.0,
    )


async def test_unraid_reboot_vm(live_mcp_client, mcptest_vm) -> None:
    """Reboot returns the VM to running state."""
    _assert_mcptest(mcptest_vm["name"])
    vm_id = mcptest_vm["id"]

    if (await _vm_state(live_mcp_client, vm_id)).lower() not in {"running", "started"}:
        pytest.skip("VM not running; can't reboot")

    await live_mcp_client.call_tool("unraid_reboot_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() in {"running", "started"},
        timeout=60.0,
    )
