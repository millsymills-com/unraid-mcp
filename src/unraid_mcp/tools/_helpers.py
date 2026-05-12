"""Shared tool helpers — context extraction, client guards, and registration decorator."""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Any

from unraid_mcp.errors import UnraidError, UnraidNotConfiguredError, UnraidReadOnlyError, handle_client_error

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastmcp import Context, FastMCP

    from unraid_mcp.clients.unraid import UnraidClient
    from unraid_mcp.config import UnraidConfig


def get_ctx(ctx: Context) -> dict[str, Any]:
    """Return the lifespan context dict from a FastMCP ``Context``.

    The lifespan yields ``{"config": UnraidConfig, "client": UnraidClient | None}``
    to match FastMCP's ``LifespanFn`` contract (see #67).
    """
    return ctx.lifespan_context


def _get_config(ctx: Context) -> UnraidConfig:
    return get_ctx(ctx)["config"]


def require_client(ctx: Context) -> UnraidClient:
    """Return the Unraid client, raising ``UnraidNotConfiguredError`` if absent."""
    client = get_ctx(ctx).get("client")
    if client is None:
        raise UnraidNotConfiguredError("UNRAID_API_KEY is not set or initial connection failed")
    return client


def require_readwrite(ctx: Context, action: str) -> UnraidClient:
    """Return the client only when the server is in read-write mode."""
    if not _get_config(ctx).is_readwrite:
        raise UnraidReadOnlyError(f"Cannot {action} in read-only mode")
    return require_client(ctx)


def require_user_mutation(ctx: Context, action: str) -> UnraidClient:
    """Return the client only in read-write mode with user mutations allowed.

    Acts as defense-in-depth on top of the ``user-mutation`` tag gating in
    ``create_server``: even if a misconfigured server forgot to disable the
    tag, the runtime check here blocks the call.
    """
    config = _get_config(ctx)
    if not config.is_readwrite:
        raise UnraidReadOnlyError(f"Cannot {action} in read-only mode")
    if not config.unraid_allow_user_mutations:
        raise UnraidReadOnlyError(
            f"Cannot {action}: user mutations are disabled (set UNRAID_ALLOW_USER_MUTATIONS=true to enable)",
        )
    return require_client(ctx)


def unraid_tool(
    mcp: FastMCP,
    **tool_kwargs: Any,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Register an MCP tool with centralized ``UnraidError`` -> ``ToolError`` mapping.

    Replaces the per-tool ``try: ... except Exception as e: handle_client_error(e)``
    boilerplate with a single decorator. Critically, the catch is narrowed to
    ``UnraidError`` so programming bugs (``KeyError``, ``AttributeError``,
    ``TypeError``, etc.) propagate to FastMCP with a full stacktrace instead
    of being disguised as "Unexpected error: ..." strings sent to the model.

    ``**tool_kwargs`` is forwarded to ``mcp.tool(...)`` unchanged, so callers
    keep their existing ``tags={"write"}``, ``annotations={"readOnlyHint": False}``
    semantics and the mode-gating in ``create_server`` continues to work.

    Usage::

        @unraid_tool(mcp, tags={"system"})
        async def unraid_get_info(ctx: Context) -> SystemInfo:
            client = require_client(ctx)
            return await client.get_info()
    """

    def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except UnraidError as e:
                handle_client_error(e)

        return mcp.tool(**tool_kwargs)(wrapper)

    return decorator
