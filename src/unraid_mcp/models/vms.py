"""Virtual machine models."""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class VmDomain(UnraidBaseModel):
    """A libvirt VM domain (UUID, name, state)."""

    uuid: str | None = None
    name: str | None = None
    state: str | None = None


class Vms(UnraidBaseModel):
    """Top-level VMs container."""

    domain: list[VmDomain] | None = None
