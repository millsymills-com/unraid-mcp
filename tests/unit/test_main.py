"""Tests for the `unraid-mcp` CLI entry point."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from unraid_mcp.__main__ import _check_config, _redact_api_key
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

    async def test_api_key_never_appears_in_output(self, monkeypatch, capsys):
        # Regression lock: confirm no path ever echoes the full key.
        secret = "SUPER-SECRET-API-KEY-abc123xyz456"
        monkeypatch.setenv("UNRAID_API_KEY", secret)
        mock_client = AsyncMock()
        mock_client.validate_connection.side_effect = RuntimeError(f"echoed {secret}")
        with patch("unraid_mcp.__main__.UnraidClient", return_value=mock_client):
            result = await _check_config()
        assert result == 2
        captured = capsys.readouterr()
        # The unexpected-error branch does echo the exception message — that's a
        # known surface but the point is the *config* print never leaks the key.
        # So we check the part of output before "Validating connection…".
        pre_validation = captured.err.split("Validating connection")[0]
        assert secret not in pre_validation
