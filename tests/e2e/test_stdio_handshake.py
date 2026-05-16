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


async def test_read_tool_round_trip(mcp_session_readwrite, mock_graphql_endpoint) -> None:
    """Calling unraid_get_info returns the structured content from the mock."""
    mock_graphql_endpoint.expect_request("/graphql", method="POST").respond_with_json(
        {
            "data": {
                "info": {
                    "os": {"hostname": "mocktower", "platform": "linux", "kernel": "6.0"},
                    "cpu": {"cores": 4, "threads": 8},
                    "memory": {"total": 1024, "free": 512},
                    "versions": {"unraid": "6.12.0"},
                }
            }
        }
    )
    result = await mcp_session_readwrite.call_tool("unraid_get_info", {})
    structured = result.structured_content
    assert structured is not None
    assert structured["os"]["hostname"] == "mocktower"


async def test_write_tool_visible_in_readwrite(mcp_session_readwrite) -> None:
    """unraid_start_container is exposed when UNRAID_MODE=readwrite."""
    tools = await mcp_session_readwrite.list_tools()
    names = {t.name for t in tools}
    assert "unraid_start_container" in names


async def test_write_tool_hidden_in_readonly(mcp_session_readonly) -> None:
    """unraid_start_container is NOT exposed when UNRAID_MODE=readonly.

    This is the most security-relevant invariant in the server: a misconfigured
    server in production must never accidentally expose mutating tools.
    """
    tools = await mcp_session_readonly.list_tools()
    names = {t.name for t in tools}
    assert "unraid_start_container" not in names
    assert "unraid_stop_container" not in names
    assert "unraid_archive_notification" not in names
