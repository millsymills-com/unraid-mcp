"""End-to-end MCP transport tests over real stdio JSON-RPC."""

from __future__ import annotations

import pytest

from tests.integration._coverage import TOOLS

pytestmark = pytest.mark.e2e


async def test_handshake_lists_every_visible_tool(mcp_session_readwrite) -> None:
    """In readwrite mode the MCP session lists every tool in the manifest."""
    tools = await mcp_session_readwrite.list_tools()
    listed_names = {t.name for t in tools}

    expected = {e.name for e in TOOLS}
    missing = expected - listed_names
    assert not missing, f"tools missing from MCP session: {sorted(missing)}"

    extra = listed_names - expected
    assert not extra, f"unknown tools listed by server: {sorted(extra)}"
