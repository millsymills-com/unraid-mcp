"""Disk and SMART models."""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class Disk(UnraidBaseModel):
    """A physical disk attached to the system.

    Fields track the Unraid API 4.32+ schema: ``temp`` was renamed to
    ``temperature``, ``interface`` to ``interface_type``, ``rotational``
    was removed (the closest live equivalent is the inverse of
    ``is_spinning``).
    """

    id: str | None = None
    name: str | None = None
    device: str | None = None
    type: str | None = None
    vendor: str | None = None
    size: str | None = None
    temperature: float | None = None
    interface_type: str | None = None
    serial_num: str | None = None
    smart_status: str | None = None
    is_spinning: bool | None = None
