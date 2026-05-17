"""Virtual machine models."""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class VmDomain(UnraidBaseModel):
    """A libvirt VM domain (id, name, state).

    Schema migration #176: ``uuid`` is ``@deprecated`` on Unraid API 4.32+
    in favour of ``id: PrefixedID!`` — VM mutations already take
    ``PrefixedID!`` so reads and writes must agree on the same key shape.
    """

    id: str | None = None
    name: str | None = None
    state: str | None = None


class Vms(UnraidBaseModel):
    """Top-level VMs container."""

    domain: list[VmDomain] | None = None
