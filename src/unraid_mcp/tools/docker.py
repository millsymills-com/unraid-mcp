"""Docker container and network tools (3 read + 5 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unraid_mcp.errors import UnraidNotFoundError
from unraid_mcp.models.docker import DockerContainer, DockerNetwork
from unraid_mcp.tools._helpers import require_client, require_readwrite, tool_error_boundary


def register_docker_tools(mcp: FastMCP) -> None:
    """Register Docker tools."""

    # ── Read tools ──────────────────────────────────────────────────────

    @mcp.tool(tags={"docker"})
    @tool_error_boundary
    async def unraid_list_containers(ctx: Context) -> list[DockerContainer]:
        """List all Docker containers with status, image, ports, and network mode."""
        client = require_client(ctx)
        return await client.list_containers()

    @mcp.tool(tags={"docker"})
    @tool_error_boundary
    async def unraid_get_container(ctx: Context, container_id: str) -> DockerContainer:
        """Get detailed info for a specific Docker container by ID or name.

        Args:
            container_id: Container ID or name (matched against the ``names`` array).
        """
        client = require_client(ctx)
        containers = await client.list_containers()
        target = container_id.lstrip("/")
        for container in containers:
            if container.id == container_id:
                return container
            names = container.names or []
            if any(name.lstrip("/") == target for name in names):
                return container
        raise UnraidNotFoundError(f"Container '{container_id}' not found")

    @mcp.tool(tags={"docker"})
    @tool_error_boundary
    async def unraid_list_docker_networks(ctx: Context) -> list[DockerNetwork]:
        """List Docker networks (id, name, driver, scope)."""
        client = require_client(ctx)
        return await client.list_docker_networks()

    # ── Write tools ─────────────────────────────────────────────────────

    @mcp.tool(tags={"write", "docker"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_error_boundary
    async def unraid_start_container(ctx: Context, container_id: str) -> dict[str, Any]:
        """Start a Docker container by ID.

        Args:
            container_id: Container ID.
        """
        client = require_readwrite(ctx, "start container")
        return await client.start_container(container_id)

    @mcp.tool(tags={"write", "docker"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_error_boundary
    async def unraid_stop_container(ctx: Context, container_id: str) -> dict[str, Any]:
        """Stop a Docker container by ID.

        Args:
            container_id: Container ID.
        """
        client = require_readwrite(ctx, "stop container")
        return await client.stop_container(container_id)

    @mcp.tool(tags={"write", "docker"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_error_boundary
    async def unraid_restart_container(ctx: Context, container_id: str) -> dict[str, Any]:
        """Restart a Docker container by ID.

        Args:
            container_id: Container ID.
        """
        client = require_readwrite(ctx, "restart container")
        return await client.restart_container(container_id)

    @mcp.tool(tags={"write", "docker"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_error_boundary
    async def unraid_pause_container(ctx: Context, container_id: str) -> dict[str, Any]:
        """Pause a running Docker container.

        Args:
            container_id: Container ID.
        """
        client = require_readwrite(ctx, "pause container")
        return await client.pause_container(container_id)

    @mcp.tool(tags={"write", "docker"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_error_boundary
    async def unraid_unpause_container(ctx: Context, container_id: str) -> dict[str, Any]:
        """Unpause a paused Docker container.

        Args:
            container_id: Container ID.
        """
        client = require_readwrite(ctx, "unpause container")
        return await client.unpause_container(container_id)
