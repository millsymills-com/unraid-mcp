"""Docker container and network models."""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class ContainerPort(UnraidBaseModel):
    """A port mapping on a Docker container."""

    ip: str | None = None
    private_port: int | None = None
    public_port: int | None = None
    type: str | None = None


class DockerContainer(UnraidBaseModel):
    """A Docker container."""

    id: str | None = None
    names: list[str] | None = None
    image: str | None = None
    image_id: str | None = None
    command: str | None = None
    created: int | None = None
    state: str | None = None
    status: str | None = None
    ports: list[ContainerPort] | None = None
    auto_start: bool | None = None
    network_mode: str | None = None


class DockerNetwork(UnraidBaseModel):
    """A Docker network."""

    id: str | None = None
    name: str | None = None
    driver: str | None = None
    scope: str | None = None
    created: str | None = None
    internal: bool | None = None
    attachable: bool | None = None
    ingress: bool | None = None
