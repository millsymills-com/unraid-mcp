"""Log file models. Mirrors ``Query.logFiles`` / ``logFile``."""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class LogFile(UnraidBaseModel):
    """Metadata for an available log file."""

    name: str | None = None
    path: str | None = None
    size: int | None = None
    modified_at: str | None = None


class LogFileContent(UnraidBaseModel):
    """A (possibly paged) slice of a log file's contents."""

    path: str | None = None
    content: str | None = None
    total_lines: int | None = None
    start_line: int | None = None
