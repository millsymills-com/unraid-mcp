"""Tool tests for the system domain."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.errors import UnraidAuthError
from unraid_mcp.models.network import AccessUrl, Cloud, Network
from unraid_mcp.models.settings import ApiConfig, ApiSettings, DisplaySettings, Service
from unraid_mcp.models.system import CpuInfo, OsInfo, SystemInfo
from unraid_mcp.models.system_time import SystemTime, TimeZoneOption
from unraid_mcp.models.vars import Vars


class TestUnraidGetInfo:
    async def test_happy_path_returns_system_info(self, client_rw):
        client, mock = client_rw
        mock.get_info.return_value = SystemInfo(
            os=OsInfo(platform="linux", hostname="tower"),
            cpu=CpuInfo(cores=8),
        )
        result = await client.call_tool("unraid_get_info")
        assert result.structured_content["os"]["platform"] == "linux"
        assert result.structured_content["os"]["hostname"] == "tower"
        assert result.structured_content["cpu"]["cores"] == 8

    async def test_auth_error_surfaces_as_tool_error(self, client_rw):
        client, mock = client_rw
        mock.get_info.side_effect = UnraidAuthError("Invalid API key", status_code=401)
        with pytest.raises(ToolError, match="Authentication failed"):
            await client.call_tool("unraid_get_info")

    async def test_unconfigured_surfaces_as_not_configured_tool_error(self, client_rw_no_key):
        with pytest.raises(ToolError, match="Unraid API not configured"):
            await client_rw_no_key.call_tool("unraid_get_info")


class TestUnraidGetFlash:
    async def test_happy_path_returns_dict(self, client_rw):
        client, mock = client_rw
        mock.get_flash.return_value = {"vendor": "SanDisk", "product": "Cruzer"}
        result = await client.call_tool("unraid_get_flash")
        assert result.structured_content == {"vendor": "SanDisk", "product": "Cruzer"}


class TestUnraidGetRegistration:
    async def test_happy_path_returns_dict(self, client_rw):
        client, mock = client_rw
        mock.get_registration.return_value = {"type": "PRO", "expires": "2099-01-01"}
        result = await client.call_tool("unraid_get_registration")
        assert result.structured_content == {"type": "PRO", "expires": "2099-01-01"}
        mock.get_registration.assert_awaited_once()

    async def test_auth_error_surfaces_as_tool_error(self, client_rw):
        client, mock = client_rw
        mock.get_registration.side_effect = UnraidAuthError("Invalid API key", status_code=401)
        with pytest.raises(ToolError, match="Authentication failed"):
            await client.call_tool("unraid_get_registration")


class TestUnraidGetConnect:
    async def test_happy_path_returns_dict(self, client_rw):
        client, mock = client_rw
        mock.get_connect.return_value = {"enabled": True, "status": "connected"}
        result = await client.call_tool("unraid_get_connect")
        assert result.structured_content == {"enabled": True, "status": "connected"}
        mock.get_connect.assert_awaited_once()


class TestUnraidGetNetwork:
    async def test_happy_path_returns_network(self, client_rw):
        client, mock = client_rw
        mock.get_network.return_value = Network(
            id="net1",
            access_urls=[AccessUrl(type="LAN", ipv4="192.168.1.1")],
        )
        result = await client.call_tool("unraid_get_network")
        assert result.structured_content["id"] == "net1"
        assert result.structured_content["accessUrls"][0]["ipv4"] == "192.168.1.1"
        mock.get_network.assert_awaited_once()


class TestUnraidGetCloud:
    async def test_happy_path_returns_cloud(self, client_rw):
        client, mock = client_rw
        mock.get_cloud.return_value = Cloud(error=None, allowed_origins=["https://example.com"])
        result = await client.call_tool("unraid_get_cloud")
        assert result.structured_content["allowedOrigins"] == ["https://example.com"]
        mock.get_cloud.assert_awaited_once()


class TestUnraidListServices:
    async def test_happy_path_returns_services(self, client_rw):
        client, mock = client_rw
        mock.list_services.return_value = [
            Service(id="nginx", name="nginx", online=True),
            Service(id="samba", name="samba", online=False),
        ]
        result = await client.call_tool("unraid_list_services")
        assert result.structured_content["result"][0]["id"] == "nginx"
        assert result.structured_content["result"][0]["online"] is True
        assert result.structured_content["result"][1]["id"] == "samba"
        mock.list_services.assert_awaited_once()

    async def test_empty_list_returns_empty_result(self, client_rw):
        client, mock = client_rw
        mock.list_services.return_value = []
        result = await client.call_tool("unraid_list_services")
        assert result.structured_content["result"] == []
        mock.list_services.assert_awaited_once()


class TestUnraidGetDisplaySettings:
    async def test_happy_path_returns_display_settings(self, client_rw):
        client, mock = client_rw
        mock.get_display_settings.return_value = DisplaySettings(id="disp1", theme="black", unit="C")
        result = await client.call_tool("unraid_get_display_settings")
        assert result.structured_content["id"] == "disp1"
        assert result.structured_content["theme"] == "black"
        assert result.structured_content["unit"] == "C"
        mock.get_display_settings.assert_awaited_once()


class TestUnraidGetApiSettings:
    async def test_happy_path_returns_api_settings(self, client_rw):
        client, mock = client_rw
        mock.get_api_settings.return_value = ApiSettings(
            id="api1",
            api=ApiConfig(version="2.0", sandbox=False),
        )
        result = await client.call_tool("unraid_get_api_settings")
        assert result.structured_content["id"] == "api1"
        assert result.structured_content["api"]["version"] == "2.0"
        mock.get_api_settings.assert_awaited_once()


class TestUnraidGetSystemTime:
    async def test_happy_path_returns_system_time(self, client_rw):
        client, mock = client_rw
        mock.get_system_time.return_value = SystemTime(
            current_time="2024-01-01T12:00:00Z",
            time_zone="America/New_York",
            use_ntp=True,
        )
        result = await client.call_tool("unraid_get_system_time")
        assert result.structured_content["timeZone"] == "America/New_York"
        assert result.structured_content["useNtp"] is True
        mock.get_system_time.assert_awaited_once()


class TestUnraidListTimezoneOptions:
    async def test_happy_path_returns_timezone_options(self, client_rw):
        client, mock = client_rw
        mock.list_timezone_options.return_value = [
            TimeZoneOption(value="America/New_York", label="Eastern Time"),
            TimeZoneOption(value="UTC", label="UTC"),
        ]
        result = await client.call_tool("unraid_list_timezone_options")
        assert result.structured_content["result"][0]["value"] == "America/New_York"
        assert result.structured_content["result"][1]["value"] == "UTC"
        mock.list_timezone_options.assert_awaited_once()

    async def test_empty_list_returns_empty_result(self, client_rw):
        client, mock = client_rw
        mock.list_timezone_options.return_value = []
        result = await client.call_tool("unraid_list_timezone_options")
        assert result.structured_content["result"] == []
        mock.list_timezone_options.assert_awaited_once()


class TestUnraidGetVars:
    async def test_happy_path_returns_vars(self, client_rw):
        client, mock = client_rw
        mock.get_vars.return_value = Vars(
            id="vars1",
            version="6.12.3",
            name="tower",
            reg_state="PRO",
        )
        result = await client.call_tool("unraid_get_vars")
        assert result.structured_content["version"] == "6.12.3"
        assert result.structured_content["name"] == "tower"
        assert result.structured_content["regState"] == "PRO"
        mock.get_vars.assert_awaited_once()
