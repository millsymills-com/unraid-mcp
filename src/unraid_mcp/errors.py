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


def handle_client_error(error: Exception) -> NoReturn:
    """Map Unraid exceptions to FastMCP ToolError with agent-readable messages.

    Each typed branch also logs at WARNING so operators watching server-side
    logs see why a tool failed — without this, fifteen GraphQL errors in a
    row produced zero trace. Unexpected errors log at ERROR with traceback.

    Raises:
        ToolError: Always raised with a descriptive message.
    """
    # If a ToolError was raised upstream, preserve it — don't re-wrap under
    # the "Unexpected error" fallback which would lose the original message.
    if isinstance(error, ToolError):
        raise error
    if isinstance(error, UnraidAuthError):
        logger.warning("tool failed: auth error (status=%s): %s", error.status_code, error)
        raise ToolError(f"Authentication failed: {error}. Check your API key.") from error
    if isinstance(error, UnraidNotFoundError):
        logger.warning("tool failed: not found: %s", error)
        raise ToolError(f"Resource not found: {error}") from error
    if isinstance(error, UnraidRateLimitError):
        logger.warning("tool failed: rate limit: %s", error)
        raise ToolError(f"Rate limit exceeded: {error}. Try again later.") from error
    if isinstance(error, UnraidConnectionError):
        logger.warning("tool failed: connection error: %s", error)
        raise ToolError(f"Connection failed: {error}. Check host and network.") from error
    if isinstance(error, UnraidReadOnlyError):
        logger.warning("tool failed: write blocked in readonly mode: %s", error)
        raise ToolError(f"Write operation blocked: {error}. Server is in read-only mode.") from error
    if isinstance(error, UnraidNotConfiguredError):
        logger.warning("tool failed: API not configured: %s", error)
        raise ToolError(f"Unraid API not configured: {error}. Set UNRAID_API_KEY.") from error
    if isinstance(error, UnraidGraphQLError):
        logger.warning("tool failed: GraphQL error: %s", error)
        raise ToolError(f"GraphQL error: {error}") from error
    if isinstance(error, UnraidError):
        logger.warning("tool failed: Unraid API error (status=%s): %s", error.status_code, error)
        raise ToolError(f"Unraid API error: {error}") from error
    # Unexpected errors — preserve the full traceback for post-mortem.
    logger.exception("Unexpected error in tool execution")
    raise ToolError(f"Unexpected error: {error}") from error
