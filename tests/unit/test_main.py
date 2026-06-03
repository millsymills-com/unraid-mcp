"""Tests for the `unraid-mcp` CLI entry point."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from unraid_mcp.__main__ import _check_config, _redact_api_key, _scrub_api_key
from unraid_mcp.errors import UnraidAuthError, UnraidConnectionError


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


class TestScrubApiKey:
    def test_none_key_returns_message_unchanged(self):
        assert _scrub_api_key("connection to host failed", None) == "connection to host failed"

    def test_empty_key_returns_message_unchanged(self):
        assert _scrub_api_key("connection to host failed", "") == "connection to host failed"

    def test_replaces_key_occurrences_with_placeholder(self):
        secret = "SUPER-SECRET-abc123"
        message = f"x-api-key: {secret} rejected by https://host/graphql?key={secret}"
        scrubbed = _scrub_api_key(message, secret)
        assert secret not in scrubbed
        assert scrubbed.count("<redacted>") == 2

    def test_leaves_non_secret_content_intact(self):
        assert _scrub_api_key("Connection refused", "k" * 20) == "Connection refused"


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

    async def test_typed_error_scrubs_key_from_wrapped_message(self, monkeypatch, capsys):
        # The typed UnraidError branch echoes the wrapped client exception. httpx could
        # embed the key (header dump, URL) in that string, so the known value must be
        # scrubbed even though the rest of the message is kept for debugging.
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
        assert "connection refused" in captured.err  # non-secret context preserved
        assert secret not in captured.err
        assert "<redacted>" in captured.err
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
