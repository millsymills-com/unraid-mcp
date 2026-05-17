"""Array, parity, and capacity models."""

from __future__ import annotations

from unraid_mcp.models.common import BigInt, UnraidBaseModel


class CapacityKilobytes(UnraidBaseModel):
    """Capacity in kilobytes."""

    free: str | None = None
    used: str | None = None
    total: str | None = None


class Capacity(UnraidBaseModel):
    """Array capacity."""

    kilobytes: CapacityKilobytes | None = None


class ArrayDisk(UnraidBaseModel):
    """A single disk in the array (data, parity, or cache)."""

    id: str | None = None
    name: str | None = None
    device: str | None = None
    size: BigInt = None
    status: str | None = None
    temp: int | None = None
    num_reads: int | None = None
    num_writes: int | None = None
    num_errors: int | None = None
    fs_size: BigInt = None
    fs_free: BigInt = None
    fs_used: BigInt = None
    type: str | None = None


class ArrayState(UnraidBaseModel):
    """Top-level array state."""

    state: str | None = None
    capacity: Capacity | None = None
    boot: ArrayDisk | None = None
    parities: list[ArrayDisk] | None = None
    disks: list[ArrayDisk] | None = None
    caches: list[ArrayDisk] | None = None


class ParityHistoryEntry(UnraidBaseModel):
    """A historical parity check run."""

    date: str | None = None
    duration: int | None = None
    speed: str | None = None
    status: str | None = None
    errors: int | None = None
