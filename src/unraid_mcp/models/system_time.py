"""System time and timezone models.

Mirrors ``Query.systemTime`` / ``Query.timeZoneOptions``.
"""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class SystemTime(UnraidBaseModel):
    """Current server time configuration."""

    current_time: str | None = None
    time_zone: str | None = None
    use_ntp: bool | None = None
    ntp_servers: list[str] | None = None


class TimeZoneOption(UnraidBaseModel):
    """An available IANA timezone option."""

    value: str | None = None
    label: str | None = None
