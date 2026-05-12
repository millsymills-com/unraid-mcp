"""Tests for Unraid MCP configuration and error mapping."""

import pytest
from fastmcp.exceptions import ToolError
from pydantic import ValidationError

from unraid_mcp.config import UnraidConfig, UnraidMode
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


class TestUnraidMode:
    def test_readonly_is_default(self):
        config = UnraidConfig(_env_file=None, unraid_api_key=None)
        assert config.unraid_mode == UnraidMode.READONLY

    def test_readwrite_mode(self):
        config = UnraidConfig(_env_file=None, unraid_mode=UnraidMode.READWRITE)
        assert config.unraid_mode == UnraidMode.READWRITE
        assert config.is_readwrite is True

    def test_readonly_mode_property(self):
        config = UnraidConfig(_env_file=None, unraid_mode=UnraidMode.READONLY)
        assert config.is_readwrite is False

    def test_invalid_mode_raises_validation_error(self):
        with pytest.raises(ValidationError):
            UnraidConfig(_env_file=None, unraid_mode="invalid")


class TestApiEnabled:
    def test_api_enabled_when_key_set(self):
        config = UnraidConfig(_env_file=None, unraid_api_key="test-key")
        assert config.api_enabled is True

    def test_api_disabled_when_no_key(self):
        config = UnraidConfig(_env_file=None, unraid_api_key=None)
        assert config.api_enabled is False

    def test_api_disabled_when_key_is_empty_string(self):
        config = UnraidConfig(_env_file=None, unraid_api_key="")
        assert config.api_enabled is False


class TestApiKeySecret:
    """`unraid_api_key` must be a SecretStr — the value must never leak via repr or model_dump."""

    SECRET = "SUPER-SECRET-API-KEY-abc123xyz456"

    def test_get_secret_value_returns_raw_string(self):
        config = UnraidConfig(_env_file=None, unraid_api_key=self.SECRET)
        assert config.unraid_api_key is not None
        assert config.unraid_api_key.get_secret_value() == self.SECRET

    def test_repr_does_not_contain_secret(self):
        config = UnraidConfig(_env_file=None, unraid_api_key=self.SECRET)
        assert self.SECRET not in repr(config)

    def test_model_dump_does_not_contain_secret(self):
        config = UnraidConfig(_env_file=None, unraid_api_key=self.SECRET)
        dumped = str(config.model_dump())
        assert self.SECRET not in dumped

    def test_env_loaded_key_is_redacted_in_repr(self, monkeypatch):
        monkeypatch.setenv("UNRAID_API_KEY", self.SECRET)
        config = UnraidConfig()
        assert self.SECRET not in repr(config)
        assert config.unraid_api_key is not None
        assert config.unraid_api_key.get_secret_value() == self.SECRET


class TestDefaults:
    def test_default_host(self):
        config = UnraidConfig(_env_file=None)
        assert config.unraid_host == "tower.local"

    def test_default_port(self):
        config = UnraidConfig(_env_file=None)
        assert config.unraid_port == 443

    def test_default_use_https(self):
        config = UnraidConfig(_env_file=None)
        assert config.unraid_use_https is True

    def test_default_verify_ssl_true(self):
        config = UnraidConfig(_env_file=None)
        assert config.unraid_verify_ssl is True

    def test_default_timeout(self):
        config = UnraidConfig(_env_file=None)
        assert config.unraid_request_timeout == 30

    def test_default_max_retries(self):
        config = UnraidConfig(_env_file=None)
        assert config.unraid_max_retries == 3


class TestUrls:
    def test_base_url_https(self):
        config = UnraidConfig(_env_file=None, unraid_host="10.0.0.5", unraid_port=8443)
        assert config.base_url == "https://10.0.0.5:8443"

    def test_base_url_http(self):
        config = UnraidConfig(_env_file=None, unraid_host="10.0.0.5", unraid_port=80, unraid_use_https=False)
        assert config.base_url == "http://10.0.0.5:80"

    def test_graphql_url(self):
        config = UnraidConfig(_env_file=None, unraid_host="tower", unraid_port=443)
        assert config.graphql_url == "https://tower:443/graphql"


class TestFieldConstraints:
    def test_port_zero_raises_validation_error(self):
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            UnraidConfig(_env_file=None, unraid_port=0)

    def test_port_above_max_raises_validation_error(self):
        with pytest.raises(ValidationError, match="less than or equal to 65535"):
            UnraidConfig(_env_file=None, unraid_port=65536)

    def test_request_timeout_zero_raises_validation_error(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            UnraidConfig(_env_file=None, unraid_request_timeout=0)

    def test_max_retries_negative_raises_validation_error(self):
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            UnraidConfig(_env_file=None, unraid_max_retries=-1)

    def test_max_retries_zero_accepted(self):
        config = UnraidConfig(_env_file=None, unraid_max_retries=0)
        assert config.unraid_max_retries == 0


class TestHandleClientError:
    def test_auth_error_mapping(self):
        with pytest.raises(Exception, match="Authentication failed"):
            handle_client_error(UnraidAuthError("Invalid API key", status_code=401))

    def test_not_found_error_mapping(self):
        with pytest.raises(Exception, match="Resource not found"):
            handle_client_error(UnraidNotFoundError("xyz not found", status_code=404))

    def test_rate_limit_error_mapping(self):
        with pytest.raises(Exception, match="Rate limit exceeded"):
            handle_client_error(UnraidRateLimitError("Too many requests", status_code=429))

    def test_connection_error_mapping(self):
        with pytest.raises(Exception, match="Connection failed"):
            handle_client_error(UnraidConnectionError("Timeout"))

    def test_readonly_error_mapping(self):
        with pytest.raises(Exception, match="Write operation blocked"):
            handle_client_error(UnraidReadOnlyError("Cannot stop array"))

    def test_not_configured_error_mapping(self):
        with pytest.raises(Exception, match="Unraid API not configured"):
            handle_client_error(UnraidNotConfiguredError("Missing key"))

    def test_graphql_error_mapping(self):
        with pytest.raises(Exception, match="GraphQL error"):
            handle_client_error(UnraidGraphQLError("Field not found"))

    def test_generic_error_mapping(self):
        with pytest.raises(Exception, match="Unraid API error"):
            handle_client_error(UnraidError("Something went wrong", status_code=500))

    def test_unexpected_error_mapping(self):
        with pytest.raises(Exception, match="Unexpected error"):
            handle_client_error(RuntimeError("Boom"))

    def test_tool_error_passthrough_not_rewrapped(self):
        original = ToolError("direct tool-authored message")
        with pytest.raises(ToolError) as exc_info:
            handle_client_error(original)
        assert exc_info.value is original
        assert "Unexpected error" not in str(exc_info.value)
