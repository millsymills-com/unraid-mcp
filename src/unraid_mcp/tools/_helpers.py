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
    return ctx.lifespan_context  # ty: ignore[invalid-return-type]


def require_client(ctx: Context) -> UnraidClient:
    """Return the Unraid client, raising ``UnraidNotConfiguredError`` if absent."""
    context = get_ctx(ctx)
    client = context.client
    if client is None:
        raise UnraidNotConfiguredError("UNRAID_API_KEY is not set or initial connection failed")
    return client  # ty: ignore[invalid-return-type]


def require_readwrite(ctx: Context, action: str) -> UnraidClient:
    """Return the client only when the server is in read-write mode."""
    context = get_ctx(ctx)
    if not context.config.is_readwrite:
        raise UnraidReadOnlyError(f"Cannot {action} in read-only mode")
    return require_client(ctx)


def require_user_mutation(ctx: Context, action: str) -> UnraidClient:
    """Return the client only in read-write mode with user mutations allowed.

    Acts as defense-in-depth on top of the ``user-mutation`` tag gating in
    ``create_server``: even if a misconfigured server forgot to disable the
    tag, the runtime check here blocks the call.
    """
    context = get_ctx(ctx)
    if not context.config.is_readwrite:
        raise UnraidReadOnlyError(f"Cannot {action} in read-only mode")
    if not context.config.unraid_allow_user_mutations:
        raise UnraidReadOnlyError(
            f"Cannot {action}: user mutations are disabled (set UNRAID_ALLOW_USER_MUTATIONS=true to enable)",
        )
    return require_client(ctx)
