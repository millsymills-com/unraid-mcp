"""Tests for handle_client_error logging and mapping."""

from __future__ import annotations

import logging

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.errors import (
    UnraidAuthError,
    UnraidConnectionError,
    UnraidError,
    UnraidGraphQLError,
    UnraidNotConfiguredError,
    UnraidNotFoundError,
    UnraidRateLimitError,
    UnraidReadOnlyError,
    handle_client_error,
)


@pytest.mark.parametrize(
    ("exc", "expected_msg_substr"),
    [
        (UnraidAuthError("bad key", status_code=401), "Authentication failed"),
        (UnraidNotFoundError("no share"), "Resource not found"),
        (UnraidRateLimitError("slow down", status_code=429), "Rate limit exceeded"),
        (UnraidConnectionError("refused"), "Connection failed"),
        (UnraidReadOnlyError("write blocked"), "Write operation blocked"),
        (UnraidNotConfiguredError("no key"), "Unraid API not configured"),
        (UnraidGraphQLError("field not found"), "GraphQL error"),
        (UnraidError("generic", status_code=418), "Unraid API error"),
    ],
)
def test_handle_client_error_maps_typed_exceptions_to_tool_error(exc, expected_msg_substr, caplog):
    with (
        caplog.at_level(logging.WARNING, logger="unraid_mcp.errors"),
        pytest.raises(ToolError, match=expected_msg_substr),
    ):
        handle_client_error(exc)
    # Every typed branch must log a WARNING so operators see failures server-side (#76).
    assert any(r.levelno == logging.WARNING for r in caplog.records), (
        f"expected WARNING log for {type(exc).__name__}, got {[r.levelname for r in caplog.records]}"
    )


def test_handle_client_error_unknown_exception_logs_error_with_traceback(caplog):
    with (
        caplog.at_level(logging.ERROR, logger="unraid_mcp.errors"),
        pytest.raises(ToolError, match="Unexpected error"),
    ):
        handle_client_error(ValueError("surprise"))
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_records, "expected ERROR log for unknown exception"
    # logger.exception attaches exc_info so traceback-aware handlers get it.
    assert error_records[0].exc_info is not None


def test_handle_client_error_preserves_tool_error():
    original = ToolError("already wrapped")
    with pytest.raises(ToolError, match="already wrapped"):
        handle_client_error(original)
