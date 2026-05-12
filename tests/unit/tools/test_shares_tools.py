"""Tool tests for the shares domain."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.errors import UnraidNotFoundError
from unraid_mcp.models.shares import Share


class TestListShares:
    async def test_returns_list(self, client_rw):
        client, mock = client_rw
        mock.list_shares.return_value = [Share(name="media", free="1TB"), Share(name="backups", free="500G")]
        result = await client.call_tool("unraid_list_shares")
        assert [s["name"] for s in result.structured_content["result"]] == ["media", "backups"]


class TestGetShare:
    async def test_lookup_delegates_to_client(self, client_rw):
        # ``Query.share`` doesn't exist on the live schema — the client's
        # ``get_share`` still encapsulates the list-then-filter so the tool
        # layer keeps a single call site for symmetry with the disk and
        # container lookups.
        client, mock = client_rw
        mock.get_share.return_value = Share(name="backups")
        result = await client.call_tool("unraid_get_share", {"name": "backups"})
        assert result.structured_content["name"] == "backups"
        mock.get_share.assert_awaited_once_with("backups")

    async def test_miss_raises_not_found(self, client_rw):
        client, mock = client_rw
        mock.get_share.side_effect = UnraidNotFoundError("Share 'nope' not found")
        with pytest.raises(ToolError, match="Resource not found"):
            await client.call_tool("unraid_get_share", {"name": "nope"})
