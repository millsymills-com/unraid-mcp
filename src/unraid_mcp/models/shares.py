"""User share models."""

from __future__ import annotations

from unraid_mcp.models.common import BigInt, UnraidBaseModel


class Share(UnraidBaseModel):
    """A user or disk share."""

    name: str | None = None
    name_orig: str | None = None
    comment: str | None = None
    free: BigInt = None
    size: BigInt = None
    used: BigInt = None
    include: list[str] | None = None
    exclude: list[str] | None = None
    cache: str | None = None
    allocator: str | None = None
    floor: str | None = None
    split_level: str | None = None
    cow: str | None = None
    color: str | None = None
    luks_status: str | None = None
