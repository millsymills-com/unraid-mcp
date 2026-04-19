"""Fixtures for tool-layer tests.

Each fixture builds a FastMCP server with `UnraidClient` replaced by an
`AsyncMock`, then exposes an in-memory `fastmcp.Client` together with the
mock so tests can set return values / side effects per test.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastmcp import Client

from unraid_mcp.server import create_server


@pytest.fixture
def mock_unraid_client():
    mock = AsyncMock()
    mock.validate_connection.return_value = None
    return mock


@pytest_asyncio.fixture
async def client_rw(monkeypatch, mock_unraid_client):
    """In-memory FastMCP client with the server in read-write mode."""
    monkeypatch.setenv("UNRAID_API_KEY", "test-key")
    monkeypatch.setenv("UNRAID_MODE", "readwrite")
    monkeypatch.setattr(
        "unraid_mcp.clients.unraid.UnraidClient",
        lambda *_a, **_kw: mock_unraid_client,
    )
    server = create_server()
    async with Client(server) as client:
        yield client, mock_unraid_client


@pytest_asyncio.fixture
async def client_ro(monkeypatch, mock_unraid_client):
    """In-memory FastMCP client with the server in read-only mode (default)."""
    monkeypatch.setenv("UNRAID_API_KEY", "test-key")
    monkeypatch.setenv("UNRAID_MODE", "readonly")
    monkeypatch.setattr(
        "unraid_mcp.clients.unraid.UnraidClient",
        lambda *_a, **_kw: mock_unraid_client,
    )
    server = create_server()
    async with Client(server) as client:
        yield client, mock_unraid_client


@pytest_asyncio.fixture
async def client_rw_no_key(monkeypatch):
    """Read-write mode but no API key configured — tools should fail with NotConfigured."""
    monkeypatch.delenv("UNRAID_API_KEY", raising=False)
    monkeypatch.setenv("UNRAID_MODE", "readwrite")
    server = create_server()
    async with Client(server) as client:
        yield client


@pytest_asyncio.fixture
async def client_rw_user_mutations(monkeypatch, mock_unraid_client):
    """Read-write mode with UNRAID_ALLOW_USER_MUTATIONS=true."""
    monkeypatch.setenv("UNRAID_API_KEY", "test-key")
    monkeypatch.setenv("UNRAID_MODE", "readwrite")
    monkeypatch.setenv("UNRAID_ALLOW_USER_MUTATIONS", "true")
    monkeypatch.setattr(
        "unraid_mcp.clients.unraid.UnraidClient",
        lambda *_a, **_kw: mock_unraid_client,
    )
    server = create_server()
    async with Client(server) as client:
        yield client, mock_unraid_client
