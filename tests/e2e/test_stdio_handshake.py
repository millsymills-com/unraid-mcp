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


async def test_graphql_error_surfaces_as_tool_error(mcp_session_readwrite, mock_graphql_endpoint) -> None:
    """A GraphQL error from the backend surfaces as a ToolError via MCP."""
    mock_graphql_endpoint.clear_all_handlers()
    mock_graphql_endpoint.expect_request("/graphql", method="POST").respond_with_json(
        {"errors": [{"message": "synthetic backend failure", "extensions": {"code": "INTERNAL_SERVER_ERROR"}}]}
    )
    from fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as exc:
        await mcp_session_readwrite.call_tool("unraid_get_info", {})
    assert "synthetic" in str(exc.value).lower() or "graphql" in str(exc.value).lower()


async def test_lifespan_shuts_down_on_session_close(mock_graphql_endpoint, monkeypatch) -> None:
    """Server starts, advertises capabilities, shuts down cleanly when stdin closes."""
    import os

    import anyio
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport
    from mcp.client import stdio

    processes = []
    original_create = stdio._create_platform_compatible_process

    async def capture_process(*args, **kwargs):
        process = await original_create(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(stdio, "_create_platform_compatible_process", capture_process)
    transport = StdioTransport(
        command="uv",
        keep_alive=False,
        args=["run", "unraid-mcp"],
        env={
            **os.environ,
            "UNRAID_HOST": "localhost",
            "UNRAID_PORT": str(mock_graphql_endpoint.port),
            "UNRAID_USE_HTTPS": "false",
            "UNRAID_VERIFY_SSL": "false",
            "UNRAID_API_KEY": "test-key",
        },
    )
    async with Client(transport) as client:
        result = await client.list_tools()
        assert result is not None
    assert len(processes) == 1
    process = processes[0]
    try:
        assert process.returncode is not None, "stdio subprocess survived the client context"
        assert process.stdin is not None
        assert process.stdout is not None
        with pytest.raises(anyio.ClosedResourceError):
            await process.stdin.send(b"")
        with pytest.raises(anyio.ClosedResourceError):
            await process.stdout.receive()
    finally:
        # Also clean up after an assertion failure, keeping the regression isolated.
        await transport.close()
