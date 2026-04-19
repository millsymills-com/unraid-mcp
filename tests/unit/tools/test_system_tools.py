"""Tool tests for the system domain."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.errors import UnraidAuthError
from unraid_mcp.models.system import CpuInfo, OsInfo, SystemInfo


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
        mock.get_flash.return_value = {"guid": "ABCD", "vendor": "SanDisk", "product": "Cruzer"}
        result = await client.call_tool("unraid_get_flash")
        assert result.structured_content == {"guid": "ABCD", "vendor": "SanDisk", "product": "Cruzer"}
