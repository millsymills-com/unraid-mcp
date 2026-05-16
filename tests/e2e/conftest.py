"""E2E fixtures: spawn unraid-mcp as a subprocess wired to a mock GraphQL server.

The subprocess speaks MCP over stdio via FastMCP's ``StdioTransport``. The
fake GraphQL endpoint is a local ``pytest_httpserver`` that returns a canned
``info`` payload, satisfying both ``validate_connection`` (sends
``QUERY_INFO``) and any tool-call probes that exercise the read path. No live
Unraid server is required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pytest_httpserver import HTTPServer

pytestmark = pytest.mark.e2e


_DEFAULT_GRAPHQL_RESPONSE: dict[str, object] = {
    "data": {"info": {"os": {"hostname": "mocktower"}}},
}


@pytest.fixture
def mock_graphql_endpoint(httpserver: HTTPServer) -> HTTPServer:
    """Local HTTP server that fakes the Unraid GraphQL endpoint.

    Registers a wildcard ``POST /graphql`` handler that returns a canned
    ``info`` payload. Tests can layer in additional expectations via
    ``httpserver.expect_request(...).respond_with_json(...)`` to override
    behaviour for specific queries.
    """
    httpserver.expect_request("/graphql", method="POST").respond_with_json(_DEFAULT_GRAPHQL_RESPONSE)
    return httpserver


def _server_env(graphql_url: str, *, mode: str = "readonly") -> dict[str, str]:
    """Build the env dict for the unraid-mcp subprocess.

    Forces plain HTTP (the mock server is not TLS), points the client at the
    mock's host/port, and sets ``UNRAID_MODE`` to gate write-tool registration.
    """
    from urllib.parse import urlparse

    parsed = urlparse(graphql_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    return {
        "UNRAID_HOST": host,
        "UNRAID_PORT": str(port),
        "UNRAID_USE_HTTPS": "false",
        "UNRAID_VERIFY_SSL": "false",
        "UNRAID_API_KEY": "test-key",
        "UNRAID_MODE": mode,
        "UNRAID_REQUEST_TIMEOUT": "5",
        "UNRAID_MAX_RETRIES": "0",
        "PATH": _inherited_path(),
    }


def _inherited_path() -> str:
    """Return the parent ``PATH`` so the subprocess can find ``uv``."""
    import os

    return os.environ.get("PATH", "")


def _build_transport(httpserver: HTTPServer, *, mode: str) -> StdioTransport:
    graphql_url = f"http://{httpserver.host}:{httpserver.port}/graphql"
    env = _server_env(graphql_url, mode=mode)
    return StdioTransport(command="uv", args=["run", "unraid-mcp"], env=env)


@pytest_asyncio.fixture
async def mcp_session_readonly(mock_graphql_endpoint: HTTPServer) -> AsyncIterator[Client]:
    """Connected FastMCP client to a read-only unraid-mcp subprocess."""
    transport = _build_transport(mock_graphql_endpoint, mode="readonly")
    async with Client(transport) as client:
        yield client


@pytest_asyncio.fixture
async def mcp_session_readwrite(mock_graphql_endpoint: HTTPServer) -> AsyncIterator[Client]:
    """Connected FastMCP client to a read-write unraid-mcp subprocess."""
    transport = _build_transport(mock_graphql_endpoint, mode="readwrite")
    async with Client(transport) as client:
        yield client
