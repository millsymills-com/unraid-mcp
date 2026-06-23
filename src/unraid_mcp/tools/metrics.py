"""Metrics tools (read-only)."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from unraid_mcp.models.metrics import Metrics
from unraid_mcp.tools._helpers import require_client, unraid_tool


def register_metrics_tools(mcp: FastMCP) -> None:
    """Register system-metrics tools."""

    @unraid_tool(mcp, tags={"metrics"})
    async def unraid_get_metrics(ctx: Context) -> Metrics:
        """Get the current CPU, memory, and temperature metrics snapshot.

        CPU (total + per-core load), memory (system + swap byte counts and
        percentages), and temperature (per-sensor readings + summary) are folded
        into one response. The unbounded per-sensor ``history`` array is not
        included — it is a streaming concern.

        Args:
            ctx: FastMCP request context.

        Returns:
            ``Metrics`` model with optional ``cpu`` / ``memory`` / ``temperature``.
        """
        client = require_client(ctx)
        return await client.get_metrics()
