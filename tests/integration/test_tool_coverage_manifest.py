"""Meta-test: registered tool surface ↔ coverage manifest parity.

These checks run in the default ``pytest`` invocation (no live env needed)
because building a FastMCP server only registers tools — it does not talk
to the Unraid API. They guarantee that ``tests/integration/_coverage.py``
stays in lockstep with the tools actually registered by
:func:`unraid_mcp.server.create_server`.
"""

from __future__ import annotations

import asyncio
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from tests.integration._coverage import TOOLS
from unraid_mcp.config import UnraidConfig, UnraidMode
from unraid_mcp.server import create_server


def _registered_tool_names() -> set[str]:
    """Return the set of tool names registered on a fresh readwrite server."""
    cfg = UnraidConfig(unraid_mode=UnraidMode.READWRITE)
    server = create_server(cfg)
    tools = asyncio.run(server._list_tools())
    return {tool.name for tool in tools}


def test_every_registered_tool_is_in_manifest() -> None:
    """Every tool registered on the server must appear in ``TOOLS``."""
    registered = _registered_tool_names()
    manifest = {tool.name for tool in TOOLS}
    missing = registered - manifest
    assert not missing, (
        f"Tools registered on the server but missing from tests/integration/_coverage.py TOOLS: {sorted(missing)}"
    )


def test_no_manifest_entry_for_unknown_tool() -> None:
    """Every entry in ``TOOLS`` must correspond to a registered tool."""
    registered = _registered_tool_names()
    manifest = {tool.name for tool in TOOLS}
    stale = manifest - registered
    assert not stale, (
        f"Manifest entries in tests/integration/_coverage.py TOOLS without a matching registered tool: {sorted(stale)}"
    )


def test_manifest_unique_names() -> None:
    """``TOOLS`` must not contain duplicate names."""
    counts = Counter(tool.name for tool in TOOLS)
    duplicates = sorted(name for name, count in counts.items() if count > 1)
    assert not duplicates, f"Duplicate names in TOOLS: {duplicates}"


@pytest.mark.xfail(reason="live tests added in Phases 6-7", strict=False)
def test_every_manifest_tool_has_a_live_test() -> None:
    """Every covered manifest entry must have at least one collected live test.

    Collects test IDs from ``tests/integration`` (and ``tests/live_write`` when
    present) and asserts that each manifest entry whose ``marker`` is not
    ``None`` is mentioned by at least one collected test ID. Entries with
    ``marker=None`` are intentionally skipped (disruptive/out-of-scope tools).
    """
    repo_root = Path(__file__).resolve().parents[2]
    test_paths = [str(repo_root / "tests" / "integration")]
    live_write_dir = repo_root / "tests" / "live_write"
    if live_write_dir.is_dir():
        test_paths.append(str(live_write_dir))

    argv = [
        "uv",
        "run",
        "pytest",
        "--collect-only",
        "-q",
        "--no-header",
        "-o",
        "addopts=",
        *test_paths,
    ]
    result = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    collected_ids = result.stdout

    missing = [tool.name for tool in TOOLS if tool.marker is not None and tool.name not in collected_ids]
    assert not missing, f"Manifest tools with no collected live test: {sorted(missing)}"
