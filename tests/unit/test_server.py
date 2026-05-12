"""Tests for server creation and mode gating."""

from unittest.mock import AsyncMock, patch

from unraid_mcp.config import UnraidConfig, UnraidMode
from unraid_mcp.errors import UnraidConnectionError
from unraid_mcp.server import create_server, make_server_lifespan


def _make_config(**overrides):
    defaults = {
        "_env_file": None,
        "unraid_api_key": "test-key",
    }
    defaults.update(overrides)
    return UnraidConfig(**defaults)


class TestCreateServer:
    def test_creates_server(self):
        config = _make_config()
        server = create_server(config)
        assert server.name == "unraid-mcp"

    def test_creates_server_without_api_key(self):
        # Server should still construct — tools will return "not configured" at call time.
        config = _make_config(unraid_api_key=None)
        server = create_server(config)
        assert server.name == "unraid-mcp"


class TestModeGating:
    async def test_write_tools_disabled_in_readonly_mode(self):
        config = _make_config(unraid_mode=UnraidMode.READONLY)
        server = create_server(config)
        tools = await server.list_tools()
        tool_names = {t.name for t in tools}
        # Write tools should not be visible
        assert "unraid_start_array" not in tool_names
        assert "unraid_stop_array" not in tool_names
        assert "unraid_start_container" not in tool_names
        assert "unraid_archive_notification" not in tool_names
        # Read tools should be visible
        assert "unraid_get_info" in tool_names
        assert "unraid_get_array" in tool_names
        assert "unraid_list_containers" in tool_names
        assert "unraid_list_vms" in tool_names
        assert "unraid_list_shares" in tool_names
        assert "unraid_get_me" in tool_names

    async def test_write_tools_enabled_in_readwrite_mode(self):
        config = _make_config(unraid_mode=UnraidMode.READWRITE)
        server = create_server(config)
        tools = await server.list_tools()
        tool_names = {t.name for t in tools}
        assert "unraid_start_array" in tool_names
        assert "unraid_stop_array" in tool_names
        assert "unraid_start_container" in tool_names
        assert "unraid_stop_container" in tool_names
        assert "unraid_start_parity_check" in tool_names
        assert "unraid_archive_notification" in tool_names
        # Read tools should still be visible
        assert "unraid_get_info" in tool_names
        assert "unraid_get_me" in tool_names

    async def test_user_account_tool_is_read_only(self):
        # Removed in #57: there is no longer a `unraid_create_user` /
        # `unraid_delete_user`. The only remaining user-domain tool is the
        # read-only `unraid_get_me`, which must be exposed in both modes
        # and the create/delete tools must never reappear.
        for mode in (UnraidMode.READONLY, UnraidMode.READWRITE):
            config = _make_config(unraid_mode=mode)
            tool_names = {t.name for t in await create_server(config).list_tools()}
            assert "unraid_get_me" in tool_names
            assert "unraid_create_user" not in tool_names
            assert "unraid_delete_user" not in tool_names
            assert "unraid_list_users" not in tool_names

    async def test_tool_count_readonly_has_fewer_tools(self):
        config_ro = _make_config(unraid_mode=UnraidMode.READONLY)
        ro_tools = await create_server(config_ro).list_tools()

        config_rw = _make_config(unraid_mode=UnraidMode.READWRITE)
        rw_tools = await create_server(config_rw).list_tools()

        assert len(ro_tools) < len(rw_tools)


class TestLifespanValidation:
    """Lifespan must not publish a client whose validation failed."""

    async def test_context_client_is_none_when_validation_fails(self):
        config = _make_config()
        mock_client = AsyncMock()
        mock_client.validate_connection.side_effect = UnraidConnectionError("refused")

        with patch("unraid_mcp.clients.unraid.UnraidClient", return_value=mock_client):
            server = create_server(config)
            async with make_server_lifespan(config)(server) as context:
                assert isinstance(context, dict)
                assert context["client"] is None

        mock_client.close.assert_awaited_once()

    async def test_context_client_is_set_when_validation_succeeds(self):
        config = _make_config()
        mock_client = AsyncMock()
        mock_client.validate_connection.return_value = None

        with patch("unraid_mcp.clients.unraid.UnraidClient", return_value=mock_client):
            server = create_server(config)
            async with make_server_lifespan(config)(server) as context:
                assert context["client"] is mock_client

        mock_client.close.assert_awaited_once()

    async def test_context_client_is_none_when_api_key_missing(self):
        config = _make_config(unraid_api_key=None)
        server = create_server(config)
        async with make_server_lifespan(config)(server) as context:
            assert context["client"] is None

    async def test_lifespan_uses_explicit_config_over_env(self, monkeypatch):
        # Regression test for #21: the config passed to create_server must
        # be the one the lifespan uses, overriding any env vars.
        monkeypatch.setenv("UNRAID_API_KEY", "env-key-should-be-ignored")
        config = _make_config(unraid_api_key=None)  # explicit: no API key
        server = create_server(config)
        async with make_server_lifespan(config)(server) as context:
            assert context["client"] is None
            assert context["config"].unraid_api_key is None


class TestSchemaDriftWarnings:
    """Startup schema-compatibility probe (#68)."""

    async def test_logs_drift_warnings_when_detected(self, caplog):
        config = _make_config()
        mock_client = AsyncMock()
        mock_client.validate_connection.return_value = None
        mock_client.check_schema_compatibility.return_value = [
            "Disk: missing fields ['temp']",
            "Flash: type missing from server schema",
        ]
        with patch("unraid_mcp.clients.unraid.UnraidClient", return_value=mock_client):
            server = create_server(config)
            with caplog.at_level("WARNING", logger="unraid_mcp.server"):
                async with make_server_lifespan(config)(server):
                    pass

        drift_lines = [r.message for r in caplog.records if "schema drift" in r.message]
        assert len(drift_lines) == 2
        summary = [r.message for r in caplog.records if "schema-drift issue(s)" in r.message]
        assert summary, "expected a summary WARNING with the drift count"

    async def test_logs_info_when_no_drift(self, caplog):
        config = _make_config()
        mock_client = AsyncMock()
        mock_client.validate_connection.return_value = None
        mock_client.check_schema_compatibility.return_value = []
        with patch("unraid_mcp.clients.unraid.UnraidClient", return_value=mock_client):
            server = create_server(config)
            with caplog.at_level("INFO", logger="unraid_mcp.server"):
                async with make_server_lifespan(config)(server):
                    pass

        assert any("Schema compatibility check passed" in r.message for r in caplog.records)

    async def test_swallows_introspection_failure(self, caplog):
        # Older servers without introspection shouldn't crash startup.
        from unraid_mcp.errors import UnraidGraphQLError

        config = _make_config()
        mock_client = AsyncMock()
        mock_client.validate_connection.return_value = None
        mock_client.check_schema_compatibility.side_effect = UnraidGraphQLError(
            "Field '__schema' not supported",
        )
        with patch("unraid_mcp.clients.unraid.UnraidClient", return_value=mock_client):
            server = create_server(config)
            with caplog.at_level("WARNING", logger="unraid_mcp.server"):
                async with make_server_lifespan(config)(server):
                    pass

        assert any("introspection unavailable" in r.message for r in caplog.records)


class TestTlsWarning:
    """Emit a warning when HTTPS is used without TLS verification."""

    async def test_warns_when_https_and_verify_disabled(self, caplog):
        config = _make_config(unraid_api_key=None, unraid_use_https=True, unraid_verify_ssl=False)
        server = create_server(config)
        with caplog.at_level("WARNING", logger="unraid_mcp.server"):
            async with make_server_lifespan(config)(server):
                pass

        assert any("TLS verification is DISABLED" in rec.message for rec in caplog.records)

    async def test_no_warning_when_https_and_verify_enabled(self, caplog):
        config = _make_config(unraid_api_key=None, unraid_use_https=True, unraid_verify_ssl=True)
        server = create_server(config)
        with caplog.at_level("WARNING", logger="unraid_mcp.server"):
            async with make_server_lifespan(config)(server):
                pass

        assert not any("TLS verification is DISABLED" in rec.message for rec in caplog.records)

    async def test_no_warning_when_http_plain(self, caplog):
        config = _make_config(unraid_api_key=None, unraid_use_https=False, unraid_verify_ssl=False)
        server = create_server(config)
        with caplog.at_level("WARNING", logger="unraid_mcp.server"):
            async with make_server_lifespan(config)(server):
                pass

        assert not any("TLS verification is DISABLED" in rec.message for rec in caplog.records)
