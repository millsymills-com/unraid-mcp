"""Tool tests for the parity domain."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.models.array import ParityHistoryEntry


class TestUnraidGetParityHistory:
    async def test_returns_list_of_entries(self, client_rw):
        client, mock = client_rw
        mock.get_parity_history.return_value = [
            ParityHistoryEntry(date="2026-01-01", duration="10h", speed="100 MB/s", errors=0),
        ]
        result = await client.call_tool("unraid_get_parity_history")
        assert len(result.structured_content["result"]) == 1
        assert result.structured_content["result"][0]["date"] == "2026-01-01"


class TestUnraidStartParityCheck:
    async def test_default_correct_false(self, client_rw):
        # Drift: parity mutations were regrouped under
        # ``parityCheck.{start,pause,resume,cancel}`` and return JSON-ish.
        client, mock = client_rw
        mock.start_parity_check.return_value = {"parityCheck": {"start": True}}
        await client.call_tool("unraid_start_parity_check")
        mock.start_parity_check.assert_awaited_once_with(correct=False)

    async def test_correct_true_is_forwarded(self, client_rw):
        client, mock = client_rw
        mock.start_parity_check.return_value = {"parityCheck": {"start": True}}
        await client.call_tool("unraid_start_parity_check", {"correct": True})
        mock.start_parity_check.assert_awaited_once_with(correct=True)

    async def test_hidden_in_readonly(self, client_ro):
        client, _ = client_ro
        with pytest.raises(ToolError, match="Unknown tool"):
            await client.call_tool("unraid_start_parity_check")


class TestParityPauseResumeCancel:
    async def test_pause_invokes_client(self, client_rw):
        client, mock = client_rw
        mock.pause_parity_check.return_value = {"parityCheck": {"pause": True}}
        await client.call_tool("unraid_pause_parity_check")
        mock.pause_parity_check.assert_awaited_once()

    async def test_resume_invokes_client(self, client_rw):
        client, mock = client_rw
        mock.resume_parity_check.return_value = {"parityCheck": {"resume": True}}
        await client.call_tool("unraid_resume_parity_check")
        mock.resume_parity_check.assert_awaited_once()

    async def test_cancel_invokes_client(self, client_rw):
        client, mock = client_rw
        mock.cancel_parity_check.return_value = {"parityCheck": {"cancel": True}}
        await client.call_tool("unraid_cancel_parity_check")
        mock.cancel_parity_check.assert_awaited_once()
