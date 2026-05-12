"""Tool tests for the disks domain."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.errors import UnraidNotFoundError
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
    async def test_lookup_delegates_to_client(self, client_rw):
        # Tool layer should issue the singular client call directly —
        # list-then-filter has moved inside :meth:`UnraidClient.get_disk`
        # so the lookup is O(1) when the live schema exposes ``Query.disk``.
        client, mock = client_rw
        mock.get_disk.return_value = Disk(id="d2", name="disk2")
        result = await client.call_tool("unraid_get_disk", {"disk_id": "d2"})
        assert result.structured_content["id"] == "d2"
        mock.get_disk.assert_awaited_once_with("d2")

    async def test_miss_raises_not_found(self, client_rw):
        client, mock = client_rw
        mock.get_disk.side_effect = UnraidNotFoundError("Disk with id 'does-not-exist' not found")
        with pytest.raises(ToolError, match="Resource not found"):
            await client.call_tool("unraid_get_disk", {"disk_id": "does-not-exist"})
