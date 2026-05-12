"""Tool tests for the array domain."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.models.array import ArrayState


class TestUnraidGetArray:
    async def test_returns_array_state(self, client_rw):
        client, mock = client_rw
        mock.get_array.return_value = ArrayState(state="STARTED", disks=[])
        result = await client.call_tool("unraid_get_array")
        assert result.structured_content["state"] == "STARTED"


class TestUnraidStartArray:
    async def test_rw_mode_invokes_client(self, client_rw):
        # Drift: array lifecycle was regrouped under
        # ``array.setState(input: {desiredState: START | STOP})``.
        client, mock = client_rw
        mock.start_array.return_value = {"array": {"setState": {"state": "STARTED"}}}
        result = await client.call_tool("unraid_start_array")
        mock.start_array.assert_awaited_once()
        assert result.structured_content["array"]["setState"]["state"] == "STARTED"

    async def test_ro_mode_hides_write_tool(self, client_ro):
        client, _ = client_ro
        with pytest.raises(ToolError, match="Unknown tool"):
            await client.call_tool("unraid_start_array")


class TestUnraidStopArray:
    async def test_rw_mode_invokes_client(self, client_rw):
        client, mock = client_rw
        mock.stop_array.return_value = {"array": {"setState": {"state": "STOPPED"}}}
        await client.call_tool("unraid_stop_array")
        mock.stop_array.assert_awaited_once()
