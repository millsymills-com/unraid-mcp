"""Exception hierarchy and error mapping for Unraid MCP server."""

from __future__ import annotations

import logging
from typing import NoReturn

from fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)


class UnraidError(Exception):
    """Base exception for all Unraid API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class UnraidAuthError(UnraidError):
    """Authentication or authorization failure (401/403)."""


class UnraidNotFoundError(UnraidError):
    """Resource not found (404 or GraphQL not-found)."""


class UnraidRateLimitError(UnraidError):
    """Rate limit exceeded (429)."""


class UnraidConnectionError(UnraidError):
    """Connection failure (timeout, DNS, network)."""


class UnraidGraphQLError(UnraidError):
    """GraphQL response contained an ``errors`` array."""


class UnraidReadOnlyError(UnraidError):
    """Write operation attempted in read-only mode."""


class UnraidNotConfiguredError(UnraidError):
    """API key was not configured but a tool was called."""


class UnraidInitFailedError(UnraidError):
    """API key was configured, but initial validation failed at startup.

    Distinct from :class:`UnraidNotConfiguredError` so operators don't get
    misdirected to recheck their env vars when the real problem is host,
    network, TLS, or an expired key.
    """


_ERROR_TEMPLATES: tuple[tuple[type[UnraidError], str, int], ...] = (
    (UnraidAuthError, "Authentication failed: {error}. Check your API key.", logging.WARNING),
    (UnraidNotFoundError, "Resource not found: {error}", logging.WARNING),
    (UnraidRateLimitError, "Rate limit exceeded: {error}. Try again later.", logging.WARNING),
    (UnraidConnectionError, "Connection failed: {error}. Check host and network.", logging.ERROR),
    (UnraidReadOnlyError, "Write operation blocked: {error}. Server is in read-only mode.", logging.WARNING),
    (UnraidNotConfiguredError, "Unraid API not configured: {error}. Set UNRAID_API_KEY.", logging.WARNING),
    (
        UnraidInitFailedError,
        "Unraid API initial connection failed: {error}. Check host, network, TLS, and key validity.",
        logging.ERROR,
    ),
    (UnraidGraphQLError, "GraphQL error: {error}", logging.WARNING),
    (UnraidError, "Unraid API error: {error}", logging.ERROR),
)


def _classify_error(error: Exception) -> ToolError:
    """Map any exception raised by the Unraid client to a typed :class:`ToolError`.

    Centralised so every tool surfaces the same agent-readable wording for a
    given failure mode and so the error-code mapping lives in one place.
    Each typed branch also emits a log record before returning so operators
    tailing the server log see every failure, not just the unexpected ones.

    Args:
        error: The exception raised inside the tool body.

    Returns:
        A ``ToolError`` chained to ``error`` via ``__cause__`` at the call
        site. ``ToolError`` instances are returned unchanged.
    """
    if isinstance(error, ToolError):
        return error
    for exc_type, template, level in _ERROR_TEMPLATES:
        if isinstance(error, exc_type):
            logger.log(level, "%s: %s", type(error).__name__, error)
            return ToolError(template.format(error=error))
    logger.exception("Unexpected error in tool execution")
    return ToolError(f"Unexpected error: {error}")


def handle_client_error(error: Exception) -> NoReturn:
    """Raise the classified :class:`ToolError` for ``error``.

    Wraps :func:`_classify_error` so call sites can ``except Exception as e:``
    then ``handle_client_error(e)`` without an extra ``raise from`` line.

    Raises:
        ToolError: Always raised, chained to ``error``.
    """
    tool_error = _classify_error(error)
    if tool_error is error:
        raise tool_error
    raise tool_error from error
