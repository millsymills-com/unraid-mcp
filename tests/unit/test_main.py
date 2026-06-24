"""Tests for the `unraid-mcp` CLI entry point."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from unraid_mcp.__main__ import _check_config, _check_schema, _redact_api_key, _safe_error_text
from unraid_mcp.errors import UnraidAuthError, UnraidConnectionError, UnraidServerError


class TestRedactApiKey:
    def test_none_shows_not_set(self):
        assert _redact_api_key(None) == "<not set>"

    def test_empty_shows_not_set(self):
        assert _redact_api_key("") == "<not set>"

    def test_reports_length_without_any_key_characters(self):
        secret = "abcdefghijklmnopqrstuvwxyz"
        redacted = _redact_api_key(secret)
        assert redacted == f"<set, {len(secret)} chars>"
        assert "abcd" not in redacted
        assert "yz" not in redacted


class TestSafeErrorText:
    def test_none_key_returns_message_unchanged(self):
        assert _safe_error_text("connection to host failed", None) == "connection to host failed"

    def test_empty_key_returns_message_unchanged(self):
        assert _safe_error_text("connection to host failed", "") == "connection to host failed"

    def test_withholds_message_containing_key(self):
        secret = "SUPER-SECRET-abc123"
        message = f"x-api-key: {secret} rejected by https://host/graphql?key={secret}"
        safe = _safe_error_text(message, secret)
        assert secret not in safe
        assert safe == "<withheld: error text contained the API key>"

    def test_keeps_message_without_key(self):
        assert _safe_error_text("Connection refused", "k" * 20) == "Connection refused"


class TestCheckConfig:
    async def test_no_api_key_exits_one(self, monkeypatch, capsys):
        monkeypatch.delenv("UNRAID_API_KEY", raising=False)
        result = await _check_config()
        assert result == 1
        captured = capsys.readouterr()
        assert "No API key configured" in captured.err
        assert captured.out == ""

    async def test_success_exits_zero(self, monkeypatch, capsys):
        monkeypatch.setenv("UNRAID_API_KEY", "verylongsecretkey-not-shown")
        mock_client = AsyncMock()
        mock_client.validate_connection.return_value = None
        with patch("unraid_mcp.__main__.UnraidClient", return_value=mock_client):
            result = await _check_config()
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == ""  # stdout reserved for stdio JSON-RPC
        assert "OK" in captured.err
        # API key must be redacted in the output: length only, no characters
        assert "verylongsecretkey-not-shown" not in captured.err
        assert "<set, 27 chars>" in captured.err
        mock_client.close.assert_awaited_once()

    async def test_validation_failure_exits_two(self, monkeypatch, capsys):
        monkeypatch.setenv("UNRAID_API_KEY", "k" * 20)
        mock_client = AsyncMock()
        mock_client.validate_connection.side_effect = UnraidConnectionError("refused")
        with patch("unraid_mcp.__main__.UnraidClient", return_value=mock_client):
            result = await _check_config()
        assert result == 2
        captured = capsys.readouterr()
        assert "FAIL" in captured.err
        assert "UnraidConnectionError" in captured.err
        assert "refused" in captured.err
        mock_client.close.assert_awaited_once()

    async def test_auth_failure_also_exits_two(self, monkeypatch, capsys):
        monkeypatch.setenv("UNRAID_API_KEY", "k" * 20)
        mock_client = AsyncMock()
        mock_client.validate_connection.side_effect = UnraidAuthError("bad key", status_code=401)
        with patch("unraid_mcp.__main__.UnraidClient", return_value=mock_client):
            result = await _check_config()
        assert result == 2
        captured = capsys.readouterr()
        assert "UnraidAuthError" in captured.err
        mock_client.close.assert_awaited_once()

    async def test_typed_error_withholds_message_containing_key(self, monkeypatch, capsys):
        # The typed UnraidError branch echoes the wrapped client exception. httpx could
        # embed the key (header dump, URL) in that string, so when the known value
        # appears the whole message is withheld — the class name still identifies it.
        secret = "SUPER-SECRET-API-KEY-abc123xyz456"
        monkeypatch.setenv("UNRAID_API_KEY", secret)
        mock_client = AsyncMock()
        mock_client.validate_connection.side_effect = UnraidConnectionError(
            f"GET https://host/graphql x-api-key={secret} -> connection refused"
        )
        with patch("unraid_mcp.__main__.UnraidClient", return_value=mock_client):
            result = await _check_config()
        assert result == 2
        captured = capsys.readouterr()
        assert "UnraidConnectionError" in captured.err
        assert secret not in captured.err
        assert "withheld" in captured.err
        mock_client.close.assert_awaited_once()

    async def test_unexpected_error_emits_type_without_message(self, monkeypatch, capsys):
        # The unexpected branch is the one preflight path not covered by length-only
        # redaction, so it must emit the exception class name and never its message —
        # a transport error could embed the API key in the message body.
        secret = "SUPER-SECRET-API-KEY-abc123xyz456"
        monkeypatch.setenv("UNRAID_API_KEY", secret)
        mock_client = AsyncMock()
        mock_client.validate_connection.side_effect = RuntimeError(f"echoed {secret}")
        with patch("unraid_mcp.__main__.UnraidClient", return_value=mock_client):
            result = await _check_config()
        assert result == 2
        captured = capsys.readouterr()
        assert "FAIL — unexpected RuntimeError" in captured.err
        assert secret not in captured.err
        assert "echoed" not in captured.err
        mock_client.close.assert_awaited_once()


class TestCheckSchema:
    """Tests for _check_schema stream-split behaviour (issue #275).

    Drift field-name lines must go to stdout only (safe for public CI posts).
    Diagnostic and error messages must go to stderr only (CI logs, not published).
    """

    async def test_no_api_key_exits_one(self, monkeypatch, capsys):
        monkeypatch.delenv("UNRAID_API_KEY", raising=False)
        result = await _check_schema()
        assert result == 1
        captured = capsys.readouterr()
        assert "No API key configured" in captured.err
        assert captured.out == ""

    async def test_no_drift_exits_zero_no_stdout(self, monkeypatch, capsys):
        monkeypatch.setenv("UNRAID_API_KEY", "k" * 20)
        mock_client = AsyncMock()
        mock_client.check_schema_compatibility.return_value = []
        with patch("unraid_mcp.__main__.UnraidClient", return_value=mock_client):
            result = await _check_schema()
        assert result == 0
        captured = capsys.readouterr()
        assert "passed" in captured.err
        assert captured.out == ""  # nothing published when schema is clean
        mock_client.close.assert_awaited_once()

    async def test_drift_lines_go_to_stdout_not_stderr(self, monkeypatch, capsys):
        monkeypatch.setenv("UNRAID_API_KEY", "k" * 20)
        mock_client = AsyncMock()
        mock_client.check_schema_compatibility.return_value = [
            "Query: missing fields ['newField']",
            "Docker: missing fields ['someField']",
        ]
        with patch("unraid_mcp.__main__.UnraidClient", return_value=mock_client):
            result = await _check_schema()
        assert result == 2
        captured = capsys.readouterr()
        # Drift field-name lines must be on stdout — safe for public posting
        assert "Query: missing fields" in captured.out
        assert "Docker: missing fields" in captured.out
        # The diagnostic header goes to stderr, not stdout
        assert "schema-drift" in captured.err.lower()
        assert "Query: missing fields" not in captured.err
        mock_client.close.assert_awaited_once()

    async def test_connection_error_stays_on_stderr_only(self, monkeypatch, capsys):
        secret = "SUPER-SECRET-API-KEY"
        monkeypatch.setenv("UNRAID_API_KEY", secret)
        raw_body = "WAF blocked: internal-host-name.local port 9999 token=abc"
        mock_client = AsyncMock()
        mock_client.check_schema_compatibility.side_effect = UnraidServerError(f"HTTP 503: {raw_body}", status_code=503)
        with patch("unraid_mcp.__main__.UnraidClient", return_value=mock_client):
            result = await _check_schema()
        assert result == 2
        captured = capsys.readouterr()
        # Error diagnostic on stderr only — never on stdout (which gets published)
        assert "Schema check failed" in captured.err
        assert captured.out == ""
        # API key must not appear on either stream
        assert secret not in captured.out
        assert secret not in captured.err
        mock_client.close.assert_awaited_once()
