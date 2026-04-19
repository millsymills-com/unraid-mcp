"""Tests for server creation and mode gating."""

from unraid_mcp.config import UnraidConfig, UnraidMode
from unraid_mcp.server import create_server


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
