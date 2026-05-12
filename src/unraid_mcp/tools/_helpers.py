"""Shared tool helpers — context extraction and client guards."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from unraid_mcp.errors import UnraidInitFailedError, UnraidNotConfiguredError, UnraidReadOnlyError

if TYPE_CHECKING:
    from fastmcp import Context

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
    """Return the Unraid client, raising a typed error if it isn't usable.

    Distinguishes between two failure modes so operators aren't sent
    chasing the wrong root cause:

    - :class:`UnraidNotConfiguredError`: no API key was supplied at startup.
    - :class:`UnraidInitFailedError`: a key was supplied but the initial
      ``validate_connection`` call raised — the message carries the
      original exception so host / TLS / auth failures stay visible.
    """
    ctx_dict = get_ctx(ctx)
    client = ctx_dict.get("client")
    if client is not None:
        return client
    init_error = ctx_dict.get("init_error")
    if init_error is not None:
        raise UnraidInitFailedError(f"{type(init_error).__name__}: {init_error}") from init_error
    raise UnraidNotConfiguredError("UNRAID_API_KEY is not set")


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
