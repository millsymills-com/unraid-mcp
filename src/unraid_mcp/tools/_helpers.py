"""Shared tool helpers — context extraction and client guards."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, TypeVar

from unraid_mcp.errors import UnraidNotConfiguredError, UnraidReadOnlyError, handle_client_error
from unraid_mcp.server import ServerContext

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastmcp import Context

    from unraid_mcp.clients.unraid import UnraidClient


_R = TypeVar("_R")


def get_ctx(ctx: Context) -> ServerContext:
    """Extract the typed lifespan context from a FastMCP ``Context``."""
    return ctx.lifespan_context  # type: ignore[return-value]


def tool_error_boundary(func: Callable[..., Awaitable[_R]]) -> Callable[..., Awaitable[_R]]:
    """Wrap an async tool so any raised exception is mapped via :func:`handle_client_error`.

    Replaces the copy-pasted ``try: ... except Exception as e: handle_client_error(e)``
    block that used to live in every tool body. ``handle_client_error`` raises
    ``ToolError``, so the wrapper itself never returns on error — the
    ``Awaitable[_R]`` return annotation describes the success path.
    """

    @functools.wraps(func)
    async def _wrapper(*args: Any, **kwargs: Any) -> _R:
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            handle_client_error(exc)

    return _wrapper


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
