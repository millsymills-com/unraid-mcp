"""System / OS / CPU / memory models."""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class OsInfo(UnraidBaseModel):
    """Operating system information."""

    platform: str | None = None
    distro: str | None = None
    release: str | None = None
    codename: str | None = None
    kernel: str | None = None
    arch: str | None = None
    hostname: str | None = None
    uptime: str | None = None


class CpuInfo(UnraidBaseModel):
    """CPU information."""

    manufacturer: str | None = None
    brand: str | None = None
    vendor: str | None = None
    family: str | None = None
    model: str | None = None
    stepping: str | None = None
    speed: float | None = None
    cores: int | None = None
    threads: int | None = None
    processors: int | None = None


class MemoryInfo(UnraidBaseModel):
    """Memory information (bytes)."""

    total: int | None = None
    free: int | None = None
    used: int | None = None
    active: int | None = None
    available: int | None = None


class BaseboardInfo(UnraidBaseModel):
    """System baseboard / motherboard info."""

    manufacturer: str | None = None
    model: str | None = None
    version: str | None = None
    serial: str | None = None


class VersionsInfo(UnraidBaseModel):
    """Versions of installed components."""

    unraid: str | None = None
    kernel: str | None = None
    openssl: str | None = None
    docker: str | None = None


class SystemInfo(UnraidBaseModel):
    """Top-level system info bundle."""

    os: OsInfo | None = None
    cpu: CpuInfo | None = None
    memory: MemoryInfo | None = None
    baseboard: BaseboardInfo | None = None
    versions: VersionsInfo | None = None
