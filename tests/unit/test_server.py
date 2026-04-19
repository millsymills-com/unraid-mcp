"""Tests for server creation and mode gating."""

from unittest.mock import AsyncMock, patch

from unraid_mcp.config import UnraidConfig, UnraidMode
from unraid_mcp.errors import UnraidConnectionError
from unraid_mcp.server import ServerContext, create_server, server_lifespan


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
        assert "unraid_delete_user" not in tool_names
        assert "unraid_archive_notification" not in tool_names
        # Read tools should be visible
        assert "unraid_get_info" in tool_names
        assert "unraid_get_array" in tool_names
        assert "unraid_list_containers" in tool_names
        assert "unraid_list_vms" in tool_names
        assert "unraid_list_shares" in tool_names

    async def test_write_tools_enabled_in_readwrite_mode(self):
        config = _make_config(unraid_mode=UnraidMode.READWRITE)
        server = create_server(config)
        tools = await server.list_tools()
        tool_names = {t.name for t in tools}
        # Write tools should be visible
        assert "unraid_start_array" in tool_names
        assert "unraid_stop_array" in tool_names
        assert "unraid_start_container" in tool_names
        assert "unraid_stop_container" in tool_names
        assert "unraid_start_parity_check" in tool_names
        assert "unraid_create_user" in tool_names
        assert "unraid_delete_user" in tool_names
        assert "unraid_archive_notification" in tool_names
        # Read tools should still be visible
        assert "unraid_get_info" in tool_names

    async def test_tool_count_readonly_has_fewer_tools(self):
        config_ro = _make_config(unraid_mode=UnraidMode.READONLY)
        ro_tools = await create_server(config_ro).list_tools()

        config_rw = _make_config(unraid_mode=UnraidMode.READWRITE)
        rw_tools = await create_server(config_rw).list_tools()

        assert len(ro_tools) < len(rw_tools)


class TestLifespanValidation:
    """Lifespan must not publish a client whose validation failed."""

    async def test_context_client_is_none_when_validation_fails(self, monkeypatch):
        monkeypatch.setenv("UNRAID_API_KEY", "test-key")
        mock_client = AsyncMock()
        mock_client.validate_connection.side_effect = UnraidConnectionError("refused")

        with patch("unraid_mcp.clients.unraid.UnraidClient", return_value=mock_client):
            server = create_server()
            async with server_lifespan(server) as context:
                assert isinstance(context, ServerContext)
                assert context.client is None

        mock_client.close.assert_awaited_once()

    async def test_context_client_is_set_when_validation_succeeds(self, monkeypatch):
        monkeypatch.setenv("UNRAID_API_KEY", "test-key")
        mock_client = AsyncMock()
        mock_client.validate_connection.return_value = None

        with patch("unraid_mcp.clients.unraid.UnraidClient", return_value=mock_client):
            server = create_server()
            async with server_lifespan(server) as context:
                assert context.client is mock_client

        mock_client.close.assert_awaited_once()

    async def test_context_client_is_none_when_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("UNRAID_API_KEY", raising=False)
        server = create_server()
        async with server_lifespan(server) as context:
            assert context.client is None
