"""Tests for log emission in :func:`unraid_mcp.errors.handle_client_error`.

Mapping tests (status code / message wording / `ToolError` passthrough) live
in :mod:`tests.unit.test_config`. This module owns the logging contract added
for GH-76: every typed branch must emit a log record at the right level
before re-raising, and the unexpected branch keeps its existing traceback
emission via ``logger.exception``.
"""

from __future__ import annotations

import logging

import pytest

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

_LOGGER_NAME = "unraid_mcp.errors"


class TestHandleClientErrorLogging:
    def test_auth_error_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
        with pytest.raises(Exception, match="Authentication failed"):
            handle_client_error(UnraidAuthError("Invalid API key", status_code=401))
        record = next(r for r in caplog.records if r.name == _LOGGER_NAME)
        assert record.levelno == logging.WARNING
        assert "UnraidAuthError" in record.getMessage()

    def test_not_found_error_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
        with pytest.raises(Exception, match="Resource not found"):
            handle_client_error(UnraidNotFoundError("missing", status_code=404))
        record = next(r for r in caplog.records if r.name == _LOGGER_NAME)
        assert record.levelno == logging.WARNING
        assert "UnraidNotFoundError" in record.getMessage()

    def test_rate_limit_error_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
        with pytest.raises(Exception, match="Rate limit exceeded"):
            handle_client_error(UnraidRateLimitError("slow down", status_code=429))
        record = next(r for r in caplog.records if r.name == _LOGGER_NAME)
        assert record.levelno == logging.WARNING
        assert "UnraidRateLimitError" in record.getMessage()

    def test_connection_error_logs_error(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.ERROR, logger=_LOGGER_NAME)
        with pytest.raises(Exception, match="Connection failed"):
            handle_client_error(UnraidConnectionError("timeout"))
        record = next(r for r in caplog.records if r.name == _LOGGER_NAME)
        assert record.levelno == logging.ERROR
        assert "UnraidConnectionError" in record.getMessage()

    def test_readonly_error_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
        with pytest.raises(Exception, match="Write operation blocked"):
            handle_client_error(UnraidReadOnlyError("blocked"))
        record = next(r for r in caplog.records if r.name == _LOGGER_NAME)
        assert record.levelno == logging.WARNING
        assert "UnraidReadOnlyError" in record.getMessage()

    def test_not_configured_error_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
        with pytest.raises(Exception, match="Unraid API not configured"):
            handle_client_error(UnraidNotConfiguredError("missing key"))
        record = next(r for r in caplog.records if r.name == _LOGGER_NAME)
        assert record.levelno == logging.WARNING
        assert "UnraidNotConfiguredError" in record.getMessage()

    def test_graphql_error_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
        with pytest.raises(Exception, match="GraphQL error"):
            handle_client_error(UnraidGraphQLError("field missing"))
        record = next(r for r in caplog.records if r.name == _LOGGER_NAME)
        assert record.levelno == logging.WARNING
        assert "UnraidGraphQLError" in record.getMessage()

    def test_generic_unraid_error_logs_error(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.ERROR, logger=_LOGGER_NAME)
        with pytest.raises(Exception, match="Unraid API error"):
            handle_client_error(UnraidError("boom", status_code=500))
        record = next(r for r in caplog.records if r.name == _LOGGER_NAME)
        assert record.levelno == logging.ERROR
        assert "UnraidError" in record.getMessage()

    def test_unexpected_error_still_logs_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.ERROR, logger=_LOGGER_NAME)
        with pytest.raises(Exception, match="Unexpected error"):
            handle_client_error(RuntimeError("kaboom"))
        record = next(r for r in caplog.records if r.name == _LOGGER_NAME)
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None
