"""Disk and SMART models."""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class Disk(UnraidBaseModel):
    """A physical disk attached to the system."""

    id: str | None = None
    name: str | None = None
    device: str | None = None
    type: str | None = None
    size: str | None = None
    temp: int | None = None
    rotational: bool | None = None
    interface: str | None = None
    serial_num: str | None = None
    smart_status: str | None = None
