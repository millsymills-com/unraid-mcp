"""Shared tool helpers — context extraction and client guards."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from unraid_mcp.errors import UnraidNotConfiguredError, UnraidReadOnlyError

if TYPE_CHECKING:
    from fastmcp import Context

    from unraid_mcp.clients.unraid import UnraidClient
    from unraid_mcp.config import UnraidConfig


def get_ctx(ctx: Context) -> dict[str, Any]:
    """Extract the lifespan context dict from a FastMCP ``Context``.

    FastMCP's lifespan contract is ``AsyncIterator[dict[str, Any]]``; we yield
    ``{"config": ..., "client": ...}`` from ``make_server_lifespan`` so tools
    index fields rather than doing attribute access on a dataclass (which
    would crash FastMCP's lifespan-composition helper).
    """
    return ctx.lifespan_context


def _require_config(ctx: Context) -> UnraidConfig:
    context = get_ctx(ctx)
    config = context.get("config")
    if config is None:
        raise UnraidNotConfiguredError("Lifespan context is missing config — server not initialized")
    return cast("UnraidConfig", config)


def require_client(ctx: Context) -> UnraidClient:
    """Return the Unraid client, raising ``UnraidNotConfiguredError`` if absent."""
    context = get_ctx(ctx)
    client = context.get("client")
    if client is None:
        raise UnraidNotConfiguredError("UNRAID_API_KEY is not set or initial connection failed")
    return cast("UnraidClient", client)


def require_readwrite(ctx: Context, action: str) -> UnraidClient:
    """Return the client only when the server is in read-write mode."""
    config = _require_config(ctx)
    if not config.is_readwrite:
        raise UnraidReadOnlyError(f"Cannot {action} in read-only mode")
    return require_client(ctx)


def require_user_mutation(ctx: Context, action: str) -> UnraidClient:
    """Return the client only in read-write mode with user mutations allowed.

    Acts as defense-in-depth on top of the ``user-mutation`` tag gating in
    ``create_server``: even if a misconfigured server forgot to disable the
    tag, the runtime check here blocks the call.
    """
    config = _require_config(ctx)
    if not config.is_readwrite:
        raise UnraidReadOnlyError(f"Cannot {action} in read-only mode")
    if not config.unraid_allow_user_mutations:
        raise UnraidReadOnlyError(
            f"Cannot {action}: user mutations are disabled (set UNRAID_ALLOW_USER_MUTATIONS=true to enable)",
        )
    return require_client(ctx)
