"""Shared tool helpers — context extraction and client guards."""

from __future__ import annotations

from typing import TYPE_CHECKING

from unraid_mcp.errors import UnraidInitFailedError, UnraidNotConfiguredError, UnraidReadOnlyError
from unraid_mcp.server import ServerContext

if TYPE_CHECKING:
    from fastmcp import Context

    from unraid_mcp.clients.unraid import UnraidClient


def get_ctx(ctx: Context) -> ServerContext:
    """Extract the typed lifespan context from a FastMCP ``Context``."""
    return ctx.lifespan_context  # type: ignore[return-value]


def require_client(ctx: Context) -> UnraidClient:
    """Return the Unraid client, raising a typed error when unavailable.

    Distinguishes three cases so operators see the right debugging direction:

    - ``UnraidInitFailedError`` — API key was set but startup validation failed
      (network, auth, TLS, schema drift). The original exception is chained.
    - ``UnraidNotConfiguredError`` — API key really is not set.
    """
    context = get_ctx(ctx)
    client = context.client
    if client is not None:
        return client  # type: ignore[return-value]
    init_error = context.init_error
    if init_error is not None:
        raise UnraidInitFailedError(
            f"{type(init_error).__name__}: {init_error}",
        ) from init_error
    raise UnraidNotConfiguredError("UNRAID_API_KEY is not set")


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
