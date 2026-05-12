"""Exception hierarchy and error mapping for Unraid MCP server."""

from __future__ import annotations

import logging
from typing import Any, NoReturn

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


class UnraidServerError(UnraidError):
    """Server-side failure (HTTP 5xx).

    Distinct from :class:`UnraidError` so the transport layer can retry
    these on the query path (idempotent) while leaving mutations alone
    (the server may have partially processed the request).
    """


class UnraidGraphQLError(UnraidError):
    """GraphQL response contained an ``errors`` array.

    Preserves the structured fields the GraphQL spec guarantees so callers
    (logs, metrics, error mappers) can distinguish ``GRAPHQL_VALIDATION_FAILED``
    from ``UNAUTHENTICATED`` or ``INTERNAL_SERVER_ERROR`` instead of grepping
    a concatenated message string.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        errors: list[dict[str, Any]] | None = None,
        path: list[Any] | None = None,
        locations: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.code = code
        self.errors: list[dict[str, Any]] = list(errors) if errors else []
        self.path = path
        self.locations = locations


class UnraidValidationError(UnraidGraphQLError):
    """GraphQL ``GRAPHQL_VALIDATION_FAILED`` - the server rejected the query.

    Distinct from :class:`UnraidGraphQLError` so the tool layer can surface an
    actionable "upgrade unraid-mcp" message instead of dumping the raw server
    stack trace at the model.
    """


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


_VALIDATION_FAILURE_MESSAGE = "The server rejected this query - upgrade unraid-mcp. GraphQL validation failed: {error}"

_ERROR_TEMPLATES: tuple[tuple[type[UnraidError], str, int], ...] = (
    (UnraidAuthError, "Authentication failed: {error}. Check your API key.", logging.WARNING),
    (UnraidNotFoundError, "Resource not found: {error}", logging.WARNING),
    (UnraidRateLimitError, "Rate limit exceeded: {error}. Try again later.", logging.WARNING),
    (UnraidConnectionError, "Connection failed: {error}. Check host and network.", logging.ERROR),
    (UnraidServerError, "Unraid server error: {error}. The server returned 5xx; often transient.", logging.WARNING),
    (UnraidReadOnlyError, "Write operation blocked: {error}. Server is in read-only mode.", logging.WARNING),
    (UnraidNotConfiguredError, "Unraid API not configured: {error}. Set UNRAID_API_KEY.", logging.WARNING),
    (
        UnraidInitFailedError,
        "Unraid API initial connection failed: {error}. Check host, network, TLS, and key validity.",
        logging.ERROR,
    ),
    (UnraidValidationError, _VALIDATION_FAILURE_MESSAGE, logging.WARNING),
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
