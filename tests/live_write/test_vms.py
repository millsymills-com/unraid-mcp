"""Live mutating tests for VM tools.

Uses the discovered mcptest-* VM. Covers start/stop/pause/resume/reboot.
Skips force_stop_vm — that's waived in the coverage manifest as disruptive.

Test function names intentionally embed the underlying tool name so the
manifest <-> live-test parity meta-test can match each tool to a test ID.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from tests.live_write.conftest import _assert_mcptest, cleanup_tool_call, wait_for_state

pytestmark = pytest.mark.live_write

_RUNNING = {"running", "started"}
_SHUTOFF = {"shutoff", "stopped", "shut off"}


async def _vm_state(live_mcp_client, vm_id: str) -> str:
    res = await live_mcp_client.call_tool("unraid_list_vms", {})
    payload = res.structured_content or {}
    for d in payload.get("domain") or []:
        if d.get("id") == vm_id:
            return d.get("state", "")
    return "missing"


async def _ensure_running(live_mcp_client, vm_id: str) -> bool:
    """Bring the VM to a running state. Returns True if this call started it."""
    if (await _vm_state(live_mcp_client, vm_id)).lower() in _RUNNING:
        return False
    await live_mcp_client.call_tool("unraid_start_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() in _RUNNING,
        timeout=20.0,
    )
    return True


async def _ensure_shutoff(live_mcp_client, vm_id: str) -> None:
    """Bring the VM to a shutoff state so a clean start can be exercised."""
    if (await _vm_state(live_mcp_client, vm_id)).lower() in _SHUTOFF:
        return
    await live_mcp_client.call_tool("unraid_stop_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() in _SHUTOFF,
        timeout=30.0,
    )


async def test_unraid_start_vm_then_unraid_stop_vm(live_mcp_client, mcptest_vm, request: pytest.FixtureRequest) -> None:
    """Start an mcptest VM, verify state, stop it, verify."""
    _assert_mcptest(mcptest_vm["name"])
    vm_id = mcptest_vm["id"]
    await _ensure_shutoff(live_mcp_client, vm_id)

    def _stop() -> None:
        cleanup_tool_call(f"unraid_stop_vm({vm_id})", "unraid_stop_vm", {"vm_id": vm_id})

    request.addfinalizer(_stop)

    await live_mcp_client.call_tool("unraid_start_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() in _RUNNING,
        timeout=20.0,
    )

    await live_mcp_client.call_tool("unraid_stop_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() in _SHUTOFF,
        timeout=30.0,
    )


async def test_unraid_pause_vm_then_unraid_resume_vm(
    live_mcp_client, mcptest_vm, request: pytest.FixtureRequest
) -> None:
    """Pause + resume a running mcptest VM."""
    _assert_mcptest(mcptest_vm["name"])
    vm_id = mcptest_vm["id"]
    started = await _ensure_running(live_mcp_client, vm_id)

    def _restore() -> None:
        cleanup_tool_call(f"unraid_resume_vm({vm_id})", "unraid_resume_vm", {"vm_id": vm_id})
        if started:
            cleanup_tool_call(f"unraid_stop_vm({vm_id})", "unraid_stop_vm", {"vm_id": vm_id})

    request.addfinalizer(_restore)

    await live_mcp_client.call_tool("unraid_pause_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() == "paused",
        timeout=15.0,
    )

    await live_mcp_client.call_tool("unraid_resume_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() in _RUNNING,
        timeout=15.0,
    )


async def test_unraid_reboot_vm(live_mcp_client, mcptest_vm, request: pytest.FixtureRequest) -> None:
    """Reboot returns the VM to running state.

    ``reboot_vm`` issues an ACPI graceful restart, which only succeeds when the
    guest runs an OS that honors the signal. The runbook's minimal mcptest VM is
    diskless, so the tool reports ``Graceful shutdown failed`` — a fixture
    limitation, not a tool defect — and the test skips. Any other error fails.
    """
    _assert_mcptest(mcptest_vm["name"])
    vm_id = mcptest_vm["id"]
    started = await _ensure_running(live_mcp_client, vm_id)

    if started:
        request.addfinalizer(lambda: cleanup_tool_call(f"unraid_stop_vm({vm_id})", "unraid_stop_vm", {"vm_id": vm_id}))

    try:
        await live_mcp_client.call_tool("unraid_reboot_vm", {"vm_id": vm_id})
    except ToolError as exc:
        if "graceful shutdown failed" in str(exc).lower():
            pytest.skip("mcptest VM is diskless; ACPI reboot needs a bootable guest OS")
        raise

    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() in _RUNNING,
        timeout=60.0,
    )
