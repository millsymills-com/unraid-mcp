"""Tool tests for the disks domain."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.models.disks import Disk


class TestUnraidListDisks:
    async def test_returns_list(self, client_rw):
        client, mock = client_rw
        mock.list_disks.return_value = [
            Disk(id="d1", name="disk1", smart_status="PASS"),
            Disk(id="d2", name="disk2", smart_status="FAIL"),
        ]
        result = await client.call_tool("unraid_list_disks")
        ids = [d["id"] for d in result.structured_content["result"]]
        assert ids == ["d1", "d2"]


class TestUnraidGetDisk:
    async def test_lookup_by_id(self, client_rw):
        client, mock = client_rw
        mock.list_disks.return_value = [Disk(id="d1", name="disk1"), Disk(id="d2", name="disk2")]
        result = await client.call_tool("unraid_get_disk", {"disk_id": "d2"})
        assert result.structured_content["id"] == "d2"

    async def test_lookup_by_name(self, client_rw):
        client, mock = client_rw
        mock.list_disks.return_value = [Disk(id="d1", name="disk1")]
        result = await client.call_tool("unraid_get_disk", {"disk_id": "disk1"})
        assert result.structured_content["name"] == "disk1"

    async def test_miss_raises_not_found(self, client_rw):
        client, mock = client_rw
        mock.list_disks.return_value = [Disk(id="d1", name="disk1")]
        with pytest.raises(ToolError, match="Resource not found"):
            await client.call_tool("unraid_get_disk", {"disk_id": "does-not-exist"})
