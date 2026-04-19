"""Shared tool helpers — context extraction and client guards."""

from __future__ import annotations

from typing import TYPE_CHECKING

from unraid_mcp.errors import UnraidNotConfiguredError, UnraidReadOnlyError
from unraid_mcp.server import ServerContext

if TYPE_CHECKING:
    from fastmcp import Context

    from unraid_mcp.clients.unraid import UnraidClient


def get_ctx(ctx: Context) -> ServerContext:
    """Extract the typed lifespan context from a FastMCP ``Context``."""
    return ctx.lifespan_context  # type: ignore[return-value]


def require_client(ctx: Context) -> UnraidClient:
    """Return the Unraid client, raising ``UnraidNotConfiguredError`` if absent."""
    context = get_ctx(ctx)
    client = context.client
    if client is None:
        raise UnraidNotConfiguredError("UNRAID_API_KEY is not set or initial connection failed")
    return client  # type: ignore[return-value]


def require_readwrite(ctx: Context, action: str) -> UnraidClient:
    """Return the client only when the server is in read-write mode."""
    context = get_ctx(ctx)
    if not context.config.is_readwrite:
        raise UnraidReadOnlyError(f"Cannot {action} in read-only mode")
    return require_client(ctx)
