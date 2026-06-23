"""Tool-layer tests for the Phase-1 read tools.

The client is an ``AsyncMock`` (see conftest), so these assert the tool wiring:
the right client method is invoked and its result is returned, and not-found
client errors map to ``ToolError``.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.errors import UnraidNotFoundError
from unraid_mcp.models.metrics import Metrics
from unraid_mcp.models.plugins import Plugin, PluginInstallOperation
from unraid_mcp.models.ups import UPSConfiguration, UPSDevice


class TestMetricsTool:
    async def test_get_metrics(self, client_rw):
        client, mock = client_rw
        mock.get_metrics.return_value = Metrics(cpu={"percentTotal": 5.0})
        result = await client.call_tool("unraid_get_metrics")
        assert result.structured_content["cpu"]["percentTotal"] == 5.0


class TestUpsTools:
    async def test_list_ups_devices(self, client_rw):
        client, mock = client_rw
        mock.list_ups_devices.return_value = [UPSDevice(id="u1", name="UPS")]
        result = await client.call_tool("unraid_list_ups_devices")
        assert result.structured_content["result"][0]["id"] == "u1"

    async def test_get_ups_device_delegates(self, client_rw):
        client, mock = client_rw
        mock.get_ups_device.return_value = UPSDevice(id="u1")
        result = await client.call_tool("unraid_get_ups_device", {"device_id": "u1"})
        assert result.structured_content["id"] == "u1"
        mock.get_ups_device.assert_awaited_once_with("u1")

    async def test_get_ups_device_miss_raises(self, client_rw):
        client, mock = client_rw
        mock.get_ups_device.side_effect = UnraidNotFoundError("UPS device with id 'x' not found")
        with pytest.raises(ToolError, match="Resource not found"):
            await client.call_tool("unraid_get_ups_device", {"device_id": "x"})

    async def test_get_ups_configuration(self, client_rw):
        client, mock = client_rw
        mock.get_ups_configuration.return_value = UPSConfiguration(service="enable")
        result = await client.call_tool("unraid_get_ups_configuration")
        assert result.structured_content["service"] == "enable"


class TestPluginTools:
    async def test_list_plugins(self, client_rw):
        client, mock = client_rw
        mock.list_plugins.return_value = [Plugin(name="dynamix", version="1.0")]
        result = await client.call_tool("unraid_list_plugins")
        assert result.structured_content["result"][0]["name"] == "dynamix"

    async def test_list_installed_plugins(self, client_rw):
        client, mock = client_rw
        mock.list_installed_unraid_plugins.return_value = ["a.plg"]
        result = await client.call_tool("unraid_list_installed_plugins")
        assert result.structured_content["result"] == ["a.plg"]

    async def test_get_plugin_install_operation_miss_raises(self, client_rw):
        client, mock = client_rw
        mock.get_plugin_install_operation.side_effect = UnraidNotFoundError("Plugin install operation 'op' not found")
        with pytest.raises(ToolError, match="Resource not found"):
            await client.call_tool("unraid_get_plugin_install_operation", {"operation_id": "op"})

    async def test_list_plugin_install_operations(self, client_rw):
        client, mock = client_rw
        mock.list_plugin_install_operations.return_value = [PluginInstallOperation(id="op1", url="http://x")]
        result = await client.call_tool("unraid_list_plugin_install_operations")
        assert result.structured_content["result"][0]["id"] == "op1"


class TestLogTools:
    async def test_read_log_file_passes_params(self, client_rw):
        from unraid_mcp.models.logs import LogFileContent

        client, mock = client_rw
        mock.read_log_file.return_value = LogFileContent(path="/p", content="x", total_lines=1)
        result = await client.call_tool("unraid_read_log_file", {"path": "/p", "lines": 10, "start_line": 5})
        assert result.structured_content["path"] == "/p"
        mock.read_log_file.assert_awaited_once_with("/p", lines=10, start_line=5)


class TestOidcTools:
    async def test_get_sso_status(self, client_rw):
        client, mock = client_rw
        mock.get_sso_status.return_value = True
        result = await client.call_tool("unraid_get_sso_status")
        assert result.structured_content["result"] is True


class TestRcloneTool:
    async def test_get_rclone_config(self, client_rw):
        from unraid_mcp.models.rclone import RCloneConfig, RCloneRemote

        client, mock = client_rw
        mock.get_rclone_config.return_value = RCloneConfig(remotes=[RCloneRemote(name="gdrive", type="drive")])
        result = await client.call_tool("unraid_get_rclone_config")
        assert result.structured_content["remotes"][0]["name"] == "gdrive"


class TestAssignableDisksTool:
    async def test_list_assignable_disks(self, client_rw):
        from unraid_mcp.models.disks import Disk

        client, mock = client_rw
        mock.list_assignable_disks.return_value = [Disk(id="d1", name="new")]
        result = await client.call_tool("unraid_list_assignable_disks")
        assert result.structured_content["result"][0]["id"] == "d1"


class TestPhase1ToolsHiddenNothing:
    """Phase-1 tools are read-only and therefore visible in read-only mode."""

    async def test_read_tools_visible_in_readonly(self, client_ro):
        client, _ = client_ro
        names = {t.name for t in await client.list_tools()}
        for name in (
            "unraid_get_metrics",
            "unraid_list_ups_devices",
            "unraid_list_plugins",
            "unraid_list_log_files",
            "unraid_get_sso_status",
            "unraid_get_rclone_config",
            "unraid_get_vars",
            "unraid_list_assignable_disks",
        ):
            assert name in names
