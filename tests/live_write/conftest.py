"""Gating, asset discovery, and shared helpers for live mutating tests.

Three layers of protection against accidental mutation:
1. pytest marker — must run with `-m live_write`
2. env flag    — UNRAID_ALLOW_LIVE_WRITES=1 required
3. mcptest_*   — every fixture asserts the asset name starts with `mcptest`
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
import traceback
from typing import TYPE_CHECKING

import pytest
from fastmcp import Client

from tests.live_write._gates import MCPTEST_PREFIX as _MCPTEST_PREFIX
from tests.live_write._gates import assert_mcptest as _assert_mcptest
from tests.live_write._gates import require_writes_enabled
from unraid_mcp.config import UnraidConfig, UnraidMode
from unraid_mcp.server import create_server

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

log = logging.getLogger(__name__)


def run_cleanup(label: str, coro_factory: Callable[[], Awaitable[object]]) -> None:
    """Run a cleanup coroutine and surface failures loudly (#177).

    Test finalizers used to wrap cleanup in ``contextlib.suppress(Exception)``,
    leaving ``mcptest_*`` assets in the wrong state on the live tower with
    zero operator signal. Cleanup is still best-effort (a raise here would
    cascade into subsequent teardown), but a failure now writes a banner to
    stderr and logs the traceback so it's impossible to miss.
    """
    try:
        asyncio.run(coro_factory())
    except Exception as exc:
        log.exception("live-write cleanup failed: %s", label)
        banner = (
            "\n" + "=" * 72 + "\n"
            f"CLEANUP FAILED — manual recovery may be required: {label}\n"
            f"  {type(exc).__name__}: {exc}\n"
            "  check the live tower for leftover mcptest_* assets\n"
            + "=" * 72
            + "\n"
            + traceback.format_exc()
            + "=" * 72
            + "\n"
        )
        sys.stderr.write(banner)
        sys.stderr.flush()


def cleanup_tool_call(label: str, tool: str, arguments: dict[str, object]) -> None:
    """Invoke one mutating tool from a finalizer using a fresh client.

    Finalizers run after the test's event loop is torn down. Reusing the
    function-scoped ``live_mcp_client`` inside ``run_cleanup``'s fresh
    ``asyncio.run`` reuses a bound httpx client across event loops, which
    hangs indefinitely on close-wait sockets. A fresh server + client per
    cleanup avoids the cross-loop reuse.
    """

    async def _do() -> None:
        cfg = UnraidConfig(unraid_mode=UnraidMode.READWRITE)
        server = create_server(cfg)
        async with Client(server) as fresh:
            await fresh.call_tool(tool, arguments)

    run_cleanup(label, _do)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Refuse to run under pytest-xdist; live writes must be serial."""
    if config.getoption("-n", default="0") not in ("0", None):
        pytest.exit(
            "tests/live_write/ may not run in parallel — re-run without -n",
            returncode=1,
        )


@pytest.fixture(scope="session", autouse=True)
def _writes_enabled() -> None:
    """Hard gate: skip the entire live_write directory unless explicitly enabled."""
    require_writes_enabled()


@pytest.fixture(scope="session", autouse=True)
def _pre_flight_banner(_writes_enabled: None) -> None:
    """Loud confirmation before any mutation runs. 3-second window for Ctrl-C."""
    cfg = UnraidConfig()
    msg = (
        "\n" + "=" * 72 + "\n"
        "LIVE WRITE TESTS ENABLED\n"
        f"  target: {cfg.graphql_url}\n"
        "  will create/archive: notifications\n"
        "  will toggle state on: mcptest-container, mcptest-vm (if present)\n"
        "  will start/pause/resume/cancel: parity checks\n"
        "Press Ctrl-C within 3 seconds to abort.\n" + "=" * 72 + "\n"
    )
    sys.stderr.write(msg)
    sys.stderr.flush()
    time.sleep(3)


@pytest.fixture
async def live_mcp_client(live_env: None) -> AsyncIterator[Client]:
    """Live FastMCP in-memory client in readwrite mode.

    Function-scoped: session-scoped async fixtures with the default
    function-scoped test loop deadlock when nested under autouse session
    fixtures (the orphan-scan dependency chain). Per-test FastMCP startup
    against the live tower is ~100 ms, so the overhead is negligible.
    Depends on ``live_env`` so the autouse ``_isolate_unraid_env`` strip
    doesn't leave ``UnraidConfig`` with an empty API key.
    """
    cfg = UnraidConfig(unraid_mode=UnraidMode.READWRITE)
    server = create_server(cfg)
    async with Client(server) as client:
        yield client


@pytest.fixture
async def mcptest_container(live_mcp_client: Client) -> dict:
    """Discover an `mcptest-*` container, fail loud if name doesn't match."""
    listing = await live_mcp_client.call_tool("unraid_list_containers", {})
    containers = listing.structured_content
    raw = containers if isinstance(containers, list) else containers.get("result", [])
    for c in raw:
        names = c.get("names") or []
        normalized = [n.lstrip("/") for n in names]
        if any(n.lower().startswith(_MCPTEST_PREFIX) for n in normalized):
            _assert_mcptest(normalized[0])
            return c
    pytest.skip(
        "skipping docker write tests: create a container whose name starts with "
        "`mcptest-` on the tower (Docker tab → Add Container, image=nginx:alpine, "
        "name=mcptest-nginx). Tests will start/stop/pause/restart it but never delete it."
    )


@pytest.fixture
async def mcptest_vm(live_mcp_client: Client) -> dict:
    """Discover an `mcptest-*` VM, fail loud if name doesn't match."""
    listing = await live_mcp_client.call_tool("unraid_list_vms", {})
    vms_payload = listing.structured_content
    domains = (vms_payload or {}).get("domain") or []
    for vm in domains:
        if (vm.get("name") or "").lower().startswith(_MCPTEST_PREFIX):
            _assert_mcptest(vm["name"])
            return vm
    pytest.skip(
        "skipping vm write tests: define a VM whose name starts with `mcptest-` on "
        "the tower (VMs tab → Add VM, minimal config, name=mcptest-vm). Tests will "
        "pause/resume/reboot it but never delete or force-stop it."
    )


async def wait_for_state[T](
    fetch: Callable[[], Awaitable[T]],
    predicate: Callable[[T], bool],
    *,
    timeout: float = 5.0,
    interval: float = 1.0,
) -> T:
    """Poll `fetch` until `predicate` returns True or `timeout` elapses."""
    deadline = time.monotonic() + timeout
    last: T | None = None
    while time.monotonic() < deadline:
        last = await fetch()
        if predicate(last):
            return last
        await asyncio.sleep(interval)
    raise AssertionError(f"state did not converge within {timeout}s (last value: {last!r}) — flake_suspect")


# ── Session-end orphan scan ────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def _orphan_scan() -> Iterator[None]:
    """At session end, list any leftover mcptest_* notifications and warn.

    Sync fixture wrapping an ``asyncio.run`` teardown so the orphan
    scan stays session-scoped without crossing pytest-asyncio's
    session-vs-function loop boundary.
    """

    async def _run_scan() -> None:
        try:
            cfg = UnraidConfig(unraid_mode=UnraidMode.READWRITE)
            server = create_server(cfg)
            async with Client(server) as scan_client:
                notifs = (await scan_client.call_tool("unraid_list_notifications", {})).structured_content
        except Exception as exc:
            log.exception("orphan scan failed")
            banner = (
                "\n" + "=" * 72 + "\n"
                "ORPHAN SCAN FAILED — could not enumerate mcptest_* assets on the live tower.\n"
                f"  {type(exc).__name__}: {exc}\n"
                "  Manually inspect the WebGUI for leftover mcptest_* containers, VMs, and notifications.\n"
                + "=" * 72
                + "\n"
                + traceback.format_exc()
                + "=" * 72
                + "\n"
            )
            sys.stderr.write(banner)
            sys.stderr.flush()
            return

        if not isinstance(notifs, list):
            return
        notif_orphans = [
            n for n in notifs if isinstance(n, dict) and str(n.get("title", "")).lower().startswith(_MCPTEST_PREFIX)
        ]

        if notif_orphans:
            msg_lines = ["\n" + "=" * 72, "ORPHAN mcptest_* ASSETS DETECTED — clean up manually:"]
            msg_lines.extend(f"  notification: {n.get('title')} (id={n.get('id')})" for n in notif_orphans)
            msg_lines.append("=" * 72 + "\n")
            sys.stderr.write("\n".join(msg_lines))
            sys.stderr.flush()

    yield
    asyncio.run(_run_scan())
