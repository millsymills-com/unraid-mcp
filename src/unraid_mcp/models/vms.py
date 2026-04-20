"""Virtual machine models."""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class VmDomain(UnraidBaseModel):
    """A libvirt VM domain.

    The Unraid API 4.32+ schema uses ``id: PrefixedID!`` where older clients
    expected ``uuid``; both are declared so responses from either era
    populate cleanly.
    """

    id: str | None = None
    uuid: str | None = None
    name: str | None = None
    state: str | None = None


class Vms(UnraidBaseModel):
    """Top-level VMs container.

    The canonical field is ``domains`` (4.32+); ``domain`` is an older alias
    kept for backward compat with pre-4.32 servers.
    """

    id: str | None = None
    domains: list[VmDomain] | None = None
    domain: list[VmDomain] | None = None
