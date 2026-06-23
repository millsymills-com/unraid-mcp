"""Log file tools (read-only)."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from unraid_mcp.models.logs import LogFile, LogFileContent
from unraid_mcp.tools._helpers import require_client, unraid_tool


def register_log_tools(mcp: FastMCP) -> None:
    """Register log file tools."""

    @unraid_tool(mcp, tags={"logs"})
    async def unraid_list_log_files(ctx: Context) -> list[LogFile]:
        """List available log files (name, path, size, last-modified time).

        Args:
            ctx: FastMCP request context.

        Returns:
            List of ``LogFile`` models.
        """
        client = require_client(ctx)
        return await client.list_log_files()

    @unraid_tool(mcp, tags={"logs"})
    async def unraid_read_log_file(
        ctx: Context,
        path: str,
        lines: int | None = None,
        start_line: int | None = None,
    ) -> LogFileContent:
        """Read the contents of a log file, optionally a paged slice.

        Args:
            ctx: FastMCP request context.
            path: Absolute path to the log file (from ``unraid_list_log_files``).
            lines: Optional number of lines to return (paging window size).
            start_line: Optional 1-indexed line to start the window at.

        Returns:
            ``LogFileContent`` with the requested slice and total line count.
        """
        client = require_client(ctx)
        return await client.read_log_file(path, lines=lines, start_line=start_line)
