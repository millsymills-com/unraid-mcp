"""Tests for tools/_helpers.py — context-extraction and typed-error distinction."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from unraid_mcp.errors import (
    UnraidConnectionError,
    UnraidInitFailedError,
    UnraidNotConfiguredError,
    UnraidReadOnlyError,
)
from unraid_mcp.server import ServerContext
from unraid_mcp.tools._helpers import require_client, require_readwrite


def _fake_ctx(server_ctx: ServerContext) -> SimpleNamespace:
    # `require_client` only touches `ctx.lifespan_context`; no need for a real
    # FastMCP Context.
    return SimpleNamespace(lifespan_context=server_ctx)


def test_require_client_raises_init_failed_when_startup_failed(unraid_config):
    """Regression for #64 — don't report 'not configured' when the key IS set
    but startup failed.
    """
    original = UnraidConnectionError("cert hostname mismatch")
    ctx = _fake_ctx(ServerContext(config=unraid_config, client=None, init_error=original))

    with pytest.raises(UnraidInitFailedError, match="cert hostname mismatch") as exc_info:
        require_client(ctx)  # type: ignore[arg-type]

    # The original exception is chained so operators see the stack.
    assert exc_info.value.__cause__ is original


def test_require_client_raises_not_configured_when_key_missing(unraid_config_no_key):
    ctx = _fake_ctx(ServerContext(config=unraid_config_no_key, client=None, init_error=None))

    with pytest.raises(UnraidNotConfiguredError, match="UNRAID_API_KEY is not set"):
        require_client(ctx)  # type: ignore[arg-type]


def test_require_client_returns_client_when_healthy(unraid_config):
    fake_client = object()
    ctx = _fake_ctx(ServerContext(config=unraid_config, client=fake_client, init_error=None))
    assert require_client(ctx) is fake_client  # type: ignore[arg-type]


def test_require_readwrite_blocks_in_readonly(unraid_config):
    ctx = _fake_ctx(ServerContext(config=unraid_config, client=object(), init_error=None))
    with pytest.raises(UnraidReadOnlyError, match="read-only mode"):
        require_readwrite(ctx, "start array")  # type: ignore[arg-type]


def test_require_readwrite_surfaces_init_error_over_readonly(unraid_config):
    # A startup failure in readwrite mode should still surface as
    # UnraidInitFailedError rather than "readonly mode" — the readwrite check
    # passes, but require_client then trips on init_error.
    from unraid_mcp.config import UnraidMode

    rw_config = unraid_config.model_copy(update={"unraid_mode": UnraidMode.READWRITE})
    original = UnraidConnectionError("refused")
    ctx = _fake_ctx(ServerContext(config=rw_config, client=None, init_error=original))

    with pytest.raises(UnraidInitFailedError, match="refused"):
        require_readwrite(ctx, "start array")  # type: ignore[arg-type]


@pytest.fixture
def unraid_config():
    from unraid_mcp.config import UnraidConfig

    return UnraidConfig(_env_file=None, unraid_api_key="test-key")


@pytest.fixture
def unraid_config_no_key():
    from unraid_mcp.config import UnraidConfig

    return UnraidConfig(_env_file=None, unraid_api_key=None)
