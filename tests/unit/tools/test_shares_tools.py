"""Tool tests for the shares domain."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.models.shares import Share


class TestListShares:
    async def test_returns_list(self, client_rw):
        client, mock = client_rw
        mock.list_shares.return_value = [Share(name="media", free="1TB"), Share(name="backups", free="500G")]
        result = await client.call_tool("unraid_list_shares")
        assert [s["name"] for s in result.structured_content["result"]] == ["media", "backups"]


class TestGetShare:
    async def test_lookup_by_name(self, client_rw):
        client, mock = client_rw
        mock.list_shares.return_value = [Share(name="media"), Share(name="backups")]
        result = await client.call_tool("unraid_get_share", {"name": "backups"})
        assert result.structured_content["name"] == "backups"

    async def test_miss_raises_not_found(self, client_rw):
        client, mock = client_rw
        mock.list_shares.return_value = [Share(name="media")]
        with pytest.raises(ToolError, match="Resource not found"):
            await client.call_tool("unraid_get_share", {"name": "nope"})
