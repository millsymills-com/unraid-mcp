"""Live MCP-tool-layer coverage for every read tool.

Complements :mod:`tests/integration/test_live_server.py` (which calls
``UnraidClient`` methods directly) by exercising the FastMCP wrapper layer:
each read tool is invoked by its registered MCP name through the in-memory
``fastmcp.Client`` transport against a real Unraid server, so the
tool → client → GraphQL path is verified end-to-end.

Gated behind the ``integration`` marker; each test fast-skips if
``UNRAID_API_KEY`` isn't set.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from fastmcp import Client

from unraid_mcp.config import UnraidConfig, UnraidMode
from unraid_mcp.server import create_server

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def live_mcp_client(live_env: None) -> AsyncIterator[Client]:
    """In-memory MCP client against a real Unraid server."""
    if not os.environ.get("UNRAID_API_KEY"):
        pytest.skip("set UNRAID_API_KEY to run live MCP-layer integration tests")
    cfg = UnraidConfig(unraid_mode=UnraidMode.READWRITE)
    server = create_server(cfg)
    async with Client(server) as client:
        yield client


async def test_unraid_get_info(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_get_info", {})
    assert result.structured_content
    assert result.structured_content["os"]["hostname"]


async def test_unraid_get_flash(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_get_flash", {})
    assert result.structured_content
    assert result.structured_content.get("vendor") or result.structured_content.get("product")


async def test_unraid_get_registration(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_get_registration", {})
    assert result.structured_content
    assert "state" in result.structured_content


async def test_unraid_get_connect(live_mcp_client: Client) -> None:
    """`get_connect` may return None or partial data if Unraid Connect is not configured."""
    result = await live_mcp_client.call_tool("unraid_get_connect", {})
    assert result is not None


async def test_unraid_get_array(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_get_array", {})
    assert result.structured_content
    assert result.structured_content.get("state")


async def test_unraid_get_parity_history(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_get_parity_history", {})
    assert result.structured_content is not None


async def test_unraid_list_disks(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_list_disks", {})
    assert result.structured_content


async def test_unraid_get_disk(live_mcp_client: Client) -> None:
    listing = await live_mcp_client.call_tool("unraid_list_disks", {})
    disks = listing.structured_content
    if not disks:
        pytest.skip("no disks reported by live server")
    first = disks[0] if isinstance(disks, list) else disks["result"][0]
    disk_id = first["id"]
    result = await live_mcp_client.call_tool("unraid_get_disk", {"disk_id": disk_id})
    assert result.structured_content
    assert result.structured_content["id"] == disk_id


async def test_unraid_list_containers(live_mcp_client: Client) -> None:
    await live_mcp_client.call_tool("unraid_list_containers", {})


async def test_unraid_get_container(live_mcp_client: Client) -> None:
    listing = await live_mcp_client.call_tool("unraid_list_containers", {})
    containers = listing.structured_content
    if not containers:
        pytest.skip("no containers on live server")
    first = containers[0] if isinstance(containers, list) else containers["result"][0]
    cid = first["id"]
    result = await live_mcp_client.call_tool("unraid_get_container", {"container_id": cid})
    assert result.structured_content
    assert result.structured_content["id"] == cid


async def test_unraid_list_docker_networks(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_list_docker_networks", {})
    assert result.structured_content


async def test_unraid_list_vms(live_mcp_client: Client) -> None:
    await live_mcp_client.call_tool("unraid_list_vms", {})


async def test_unraid_list_shares(live_mcp_client: Client) -> None:
    await live_mcp_client.call_tool("unraid_list_shares", {})


async def test_unraid_get_share(live_mcp_client: Client) -> None:
    listing = await live_mcp_client.call_tool("unraid_list_shares", {})
    shares = listing.structured_content
    if not shares:
        pytest.skip("no shares on live server")
    first = shares[0] if isinstance(shares, list) else shares["result"][0]
    name = first["name"]
    result = await live_mcp_client.call_tool("unraid_get_share", {"name": name})
    assert result.structured_content
    assert result.structured_content["name"] == name


async def test_unraid_get_me(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_get_me", {})
    assert result.structured_content
    assert result.structured_content.get("name") or result.structured_content.get("id")


async def test_unraid_list_notifications(live_mcp_client: Client) -> None:
    await live_mcp_client.call_tool("unraid_list_notifications", {})
