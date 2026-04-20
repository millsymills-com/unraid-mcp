"""Parity check tools (1 read + 4 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unraid_mcp.models.array import ParityHistoryEntry
from unraid_mcp.tools._helpers import require_client, require_readwrite, tool_error_boundary


def register_parity_tools(mcp: FastMCP) -> None:
    """Register parity check tools."""

    @mcp.tool(tags={"array", "parity"})
    @tool_error_boundary
    async def unraid_get_parity_history(ctx: Context) -> list[ParityHistoryEntry]:
        """List historical parity check runs (date, duration, speed, errors)."""
        client = require_client(ctx)
        return await client.get_parity_history()

    @mcp.tool(tags={"write", "array", "parity"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_error_boundary
    async def unraid_start_parity_check(ctx: Context, correct: bool = False) -> dict[str, Any]:
        """Start a parity check.

        Args:
            correct: If True, write corrections to parity. If False (default), report errors only.
        """
        client = require_readwrite(ctx, "start parity check")
        return await client.start_parity_check(correct=correct)

    @mcp.tool(tags={"write", "array", "parity"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_error_boundary
    async def unraid_pause_parity_check(ctx: Context) -> dict[str, Any]:
        """Pause an in-progress parity check."""
        client = require_readwrite(ctx, "pause parity check")
        return await client.pause_parity_check()

    @mcp.tool(tags={"write", "array", "parity"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_error_boundary
    async def unraid_resume_parity_check(ctx: Context) -> dict[str, Any]:
        """Resume a paused parity check."""
        client = require_readwrite(ctx, "resume parity check")
        return await client.resume_parity_check()

    @mcp.tool(tags={"write", "array", "parity"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_error_boundary
    async def unraid_cancel_parity_check(ctx: Context) -> dict[str, Any]:
        """Cancel an in-progress parity check."""
        client = require_readwrite(ctx, "cancel parity check")
        return await client.cancel_parity_check()
