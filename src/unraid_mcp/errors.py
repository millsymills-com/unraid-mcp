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

    Raises:
        ToolError: Always raised with a descriptive message.
    """
    if isinstance(error, UnraidAuthError):
        raise ToolError(f"Authentication failed: {error}. Check your API key.") from error
    if isinstance(error, UnraidNotFoundError):
        raise ToolError(f"Resource not found: {error}") from error
    if isinstance(error, UnraidRateLimitError):
        raise ToolError(f"Rate limit exceeded: {error}. Try again later.") from error
    if isinstance(error, UnraidConnectionError):
        raise ToolError(f"Connection failed: {error}. Check host and network.") from error
    if isinstance(error, UnraidReadOnlyError):
        raise ToolError(f"Write operation blocked: {error}. Server is in read-only mode.") from error
    if isinstance(error, UnraidNotConfiguredError):
        raise ToolError(f"Unraid API not configured: {error}. Set UNRAID_API_KEY.") from error
    if isinstance(error, UnraidGraphQLError):
        raise ToolError(f"GraphQL error: {error}") from error
    if isinstance(error, UnraidError):
        raise ToolError(f"Unraid API error: {error}") from error
    # Unexpected errors
    logger.exception("Unexpected error in tool execution")
    raise ToolError(f"Unexpected error: {error}") from error
