"""Meta-test: registered tool surface ↔ coverage manifest parity.

These checks run in the default ``pytest`` invocation (no live env needed)
because building a FastMCP server only registers tools — it does not talk
to the Unraid API. They guarantee that ``tests/integration/_coverage.py``
stays in lockstep with the tools actually registered by
:func:`unraid_mcp.server.create_server`.
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from pathlib import Path

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


_CALL_TOOL_RE = re.compile(r"""call_tool\(\s*['"](?P<name>unraid_[a-zA-Z0-9_]+)['"]""")


def _tools_invoked_in_test_files() -> set[str]:
    """Return the set of tool names actually invoked via ``call_tool`` in test files.

    Earlier versions of this test used substring-matching against pytest's
    ``--collect-only`` output, which could false-match a logging test against
    an unrelated tool name (e.g., ``test_logging_unraid_start_container_*``
    would falsely cover ``unraid_start_container``). Walking the test source
    and matching the literal ``call_tool("unraid_…",`` invocation is precise:
    a manifest tool counts as covered only when it is actually called (#180).
    """
    repo_root = Path(__file__).resolve().parents[2]
    test_dirs = [repo_root / "tests" / "integration", repo_root / "tests" / "live_write"]
    invoked: set[str] = set()
    for test_dir in test_dirs:
        if not test_dir.is_dir():
            continue
        for path in test_dir.rglob("*.py"):
            invoked.update(match.group("name") for match in _CALL_TOOL_RE.finditer(path.read_text(encoding="utf-8")))
    return invoked


def test_every_manifest_tool_has_a_live_test() -> None:
    """Every covered manifest entry must be invoked by at least one test file.

    Matches each tool name to a literal ``call_tool("unraid_…", …)`` invocation
    in ``tests/integration/`` or ``tests/live_write/``. Entries with
    ``marker=None`` are intentionally skipped (disruptive/out-of-scope tools).
    """
    invoked = _tools_invoked_in_test_files()
    missing = sorted(tool.name for tool in TOOLS if tool.marker is not None and tool.name not in invoked)
    assert not missing, (
        f'Manifest tools with no `call_tool("…", …)` invocation in tests/integration or tests/live_write: {missing}'
    )
