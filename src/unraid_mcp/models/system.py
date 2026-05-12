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
    # GraphQL schema models stepping as Int; accept either Int or legacy String.
    stepping: int | str | None = None
    speed: float | None = None
    cores: int | None = None
    threads: int | None = None
    processors: int | None = None


class MemoryLayoutEntry(UnraidBaseModel):
    """One DIMM entry in ``info.memory.layout`` (Unraid API 4.32+)."""

    size: int | None = None
    type: str | None = None
    clock_speed: int | None = None
    form_factor: str | None = None
    manufacturer: str | None = None
    part_num: str | None = None
    serial_num: str | None = None
    bank: str | None = None


class MemoryInfo(UnraidBaseModel):
    """Memory information.

    The Unraid API 4.32+ schema dropped aggregated totals in favor of
    per-DIMM ``layout`` entries. Sum the sizes from ``layout`` to
    reconstruct total RAM.
    """

    id: str | None = None
    layout: list[MemoryLayoutEntry] | None = None


class BaseboardInfo(UnraidBaseModel):
    """System baseboard / motherboard info."""

    manufacturer: str | None = None
    model: str | None = None
    version: str | None = None
    serial: str | None = None


class CoreVersions(UnraidBaseModel):
    """Core Unraid component versions (``info.versions.core``)."""

    unraid: str | None = None
    kernel: str | None = None
    api: str | None = None


class PackageVersions(UnraidBaseModel):
    """Installed third-party package versions (``info.versions.packages``)."""

    openssl: str | None = None
    docker: str | None = None
    node: str | None = None
    npm: str | None = None
    nginx: str | None = None
    php: str | None = None
    git: str | None = None
    pm2: str | None = None


class VersionsInfo(UnraidBaseModel):
    """Versions of installed components, grouped by the Unraid API 4.32+ schema."""

    id: str | None = None
    core: CoreVersions | None = None
    packages: PackageVersions | None = None


class SystemInfo(UnraidBaseModel):
    """Top-level system info bundle."""

    id: str | None = None
    os: OsInfo | None = None
    cpu: CpuInfo | None = None
    memory: MemoryInfo | None = None
    baseboard: BaseboardInfo | None = None
    versions: VersionsInfo | None = None
