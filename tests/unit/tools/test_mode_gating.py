"""Behavioural tests for the runtime mode-gating guards.

The sibling fixture-based tests cover registration visibility (write tools
are absent from `list_tools()` in readonly mode). These tests exercise the
defense-in-depth path: even when a write tool is *registered*, the
``require_readwrite`` and ``require_client`` helpers must still refuse to
return a client when the runtime context disagrees.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.lifespan import lifespan as fastmcp_lifespan

from unraid_mcp.config import UnraidConfig
from unraid_mcp.errors import UnraidNotConfiguredError, UnraidReadOnlyError
from unraid_mcp.tools._helpers import require_client, require_readwrite, require_user_mutation
from unraid_mcp.tools.array import register_array_tools


def _fake_ctx(*, config: UnraidConfig, client: object | None) -> SimpleNamespace:
    """Build a minimal FastMCP-Context stand-in.

    The helpers only read ``ctx.lifespan_context`` and treat it as the dict
    the lifespan yields (see ``server.make_server_lifespan``), so a
    `SimpleNamespace` with that attribute is enough.
    """
    return SimpleNamespace(lifespan_context={"config": config, "client": client})


class TestRequireClient:
    def test_returns_client_when_configured(self):
        config = UnraidConfig(unraid_api_key="k")
        stub = object()
        ctx = _fake_ctx(config=config, client=stub)
        assert require_client(ctx) is stub

    def test_raises_when_client_missing(self):
        config = UnraidConfig(unraid_api_key="k")
        ctx = _fake_ctx(config=config, client=None)
        with pytest.raises(UnraidNotConfiguredError, match="not set or initial connection failed"):
            require_client(ctx)


class TestRequireReadwrite:
    def test_returns_client_in_readwrite_mode(self):
        config = UnraidConfig(unraid_api_key="k", unraid_mode="readwrite")
        stub = object()
        ctx = _fake_ctx(config=config, client=stub)
        assert require_readwrite(ctx, "start array") is stub

    def test_raises_readonly_error_in_readonly_mode(self):
        config = UnraidConfig(unraid_api_key="k", unraid_mode="readonly")
        ctx = _fake_ctx(config=config, client=object())
        with pytest.raises(UnraidReadOnlyError, match="Cannot start array in read-only mode"):
            require_readwrite(ctx, "start array")

    def test_readonly_check_fires_before_client_check(self):
        """A readonly server with no client still reports the readonly cause first."""
        config = UnraidConfig(unraid_api_key="k", unraid_mode="readonly")
        ctx = _fake_ctx(config=config, client=None)
        with pytest.raises(UnraidReadOnlyError):
            require_readwrite(ctx, "stop array")


class TestRequireUserMutation:
    def test_returns_client_when_fully_enabled(self):
        config = UnraidConfig(
            unraid_api_key="k",
            unraid_mode="readwrite",
            unraid_allow_user_mutations=True,
        )
        stub = object()
        ctx = _fake_ctx(config=config, client=stub)
        assert require_user_mutation(ctx, "create user") is stub

    def test_raises_in_readonly_mode(self):
        config = UnraidConfig(
            unraid_api_key="k",
            unraid_mode="readonly",
            unraid_allow_user_mutations=True,
        )
        ctx = _fake_ctx(config=config, client=object())
        with pytest.raises(UnraidReadOnlyError, match="read-only mode"):
            require_user_mutation(ctx, "create user")

    def test_raises_when_user_mutations_disabled_in_readwrite(self):
        config = UnraidConfig(
            unraid_api_key="k",
            unraid_mode="readwrite",
            unraid_allow_user_mutations=False,
        )
        ctx = _fake_ctx(config=config, client=object())
        with pytest.raises(UnraidReadOnlyError, match="UNRAID_ALLOW_USER_MUTATIONS"):
            require_user_mutation(ctx, "delete user")


class TestRuntimeGuardEndToEnd:
    """Exercise the runtime guard inside a registered write tool.

    Skips the ``server.create_server`` call so ``mcp.disable(tags={"write"})``
    is never applied — the write tool is therefore visible to the client and
    the only thing blocking the call is ``require_readwrite`` itself. This is
    what would still fire if the static gate were ever removed by mistake.
    """

    @pytest.fixture
    def mock_client(self):
        client = AsyncMock()
        client.start_array.return_value = {"startArray": {"state": "STARTED"}}
        return client

    def _build_server(self, *, config: UnraidConfig, client: object | None) -> FastMCP:
        @fastmcp_lifespan
        async def _lifespan(_server):
            yield {"config": config, "client": client}

        mcp = FastMCP(name="test-runtime-guard", lifespan=_lifespan)
        register_array_tools(mcp)
        return mcp

    async def test_write_tool_blocked_when_lifespan_is_readonly(self, mock_client):
        config = UnraidConfig(unraid_api_key="k", unraid_mode="readonly")
        server = self._build_server(config=config, client=mock_client)
        async with Client(server) as fastmcp_client:
            with pytest.raises(ToolError, match="read-only mode"):
                await fastmcp_client.call_tool("unraid_start_array")
        mock_client.start_array.assert_not_awaited()

    async def test_write_tool_blocked_when_client_unconfigured(self, mock_client):
        config = UnraidConfig(unraid_api_key="k", unraid_mode="readwrite")
        server = self._build_server(config=config, client=None)
        async with Client(server) as fastmcp_client:
            with pytest.raises(ToolError, match="not configured"):
                await fastmcp_client.call_tool("unraid_start_array")
        mock_client.start_array.assert_not_awaited()
