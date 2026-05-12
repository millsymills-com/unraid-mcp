"""Tests for the ``unraid_tool`` registration decorator (#74).

Verifies the decorator centralises ``UnraidError`` -> ``ToolError`` mapping
without swallowing programming bugs (``KeyError``, ``AttributeError``, etc.).
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.errors import UnraidAuthError


class TestDecoratorNarrowCatch:
    async def test_unraid_error_maps_to_tool_error(self, client_rw):
        # Regression for #74: UnraidError subclasses still map to ToolError
        # via the centralised handler.
        client, mock = client_rw
        mock.get_info.side_effect = UnraidAuthError("Invalid API key", status_code=401)
        with pytest.raises(ToolError, match="Authentication failed"):
            await client.call_tool("unraid_get_info")

    async def test_programming_bug_is_not_swallowed_as_tool_error(self, client_rw):
        # Regression for #74: the decorator narrows the catch to UnraidError
        # only, so a KeyError raised inside the tool body propagates as a
        # programming bug with full stacktrace instead of being disguised as
        # "Unexpected error: ..." sent to the model.
        client, mock = client_rw
        mock.get_info.side_effect = KeyError("missing_key")
        # FastMCP wraps any non-ToolError exception with its own error; what
        # matters here is that we don't see the legacy "Unexpected error"
        # ToolError wording — that proves the catch was narrowed.
        with pytest.raises(Exception) as excinfo:  # noqa: PT011  # FastMCP error class is private
            await client.call_tool("unraid_get_info")
        assert "Unexpected error" not in str(excinfo.value)
