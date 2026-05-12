"""Docker container and network tools (3 read + 5 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unraid_mcp.models.docker import DockerContainer, DockerNetwork
from unraid_mcp.tools._helpers import require_client, require_readwrite, unraid_tool


def register_docker_tools(mcp: FastMCP) -> None:
    """Register Docker tools."""

    # ── Read tools ──────────────────────────────────────────────────────

    @unraid_tool(mcp, tags={"docker"})
    async def unraid_list_containers(ctx: Context) -> list[DockerContainer]:
        """List all Docker containers with status, image, ports, and network mode.

        Args:
            ctx: FastMCP request context.

        Returns:
            List of ``DockerContainer`` models, one per container known to Docker.
        """
        client = require_client(ctx)
        return await client.list_containers()

    @unraid_tool(mcp, tags={"docker"})
    async def unraid_get_container(ctx: Context, container_id: str) -> DockerContainer:
        """Get detailed info for a specific Docker container by ID or name.

        Args:
            ctx: FastMCP request context.
            container_id: Container ID or name (matched against the ``names`` array).

        Returns:
            ``DockerContainer`` model for the matching container.
        """
        client = require_client(ctx)
        return await client.get_container(container_id)

    @unraid_tool(mcp, tags={"docker"})
    async def unraid_list_docker_networks(ctx: Context) -> list[DockerNetwork]:
        """List Docker networks (id, name, driver, scope).

        Args:
            ctx: FastMCP request context.

        Returns:
            List of ``DockerNetwork`` models, one per Docker network.
        """
        client = require_client(ctx)
        return await client.list_docker_networks()

    # ── Write tools ─────────────────────────────────────────────────────

    @unraid_tool(mcp, tags={"write", "docker"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unraid_start_container(ctx: Context, container_id: str) -> dict[str, Any]:
        """Start a Docker container by ID.

        Args:
            ctx: FastMCP request context.
            container_id: Container ID.

        Returns:
            Raw GraphQL mutation response payload.
        """
        client = require_readwrite(ctx, "start container")
        return await client.start_container(container_id)

    @unraid_tool(mcp, tags={"write", "docker"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    async def unraid_stop_container(ctx: Context, container_id: str) -> dict[str, Any]:
        """Stop a Docker container by ID.

        Args:
            ctx: FastMCP request context.
            container_id: Container ID.

        Returns:
            Raw GraphQL mutation response payload.
        """
        client = require_readwrite(ctx, "stop container")
        return await client.stop_container(container_id)

    @unraid_tool(mcp, tags={"write", "docker"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unraid_restart_container(ctx: Context, container_id: str) -> dict[str, Any]:
        """Restart a Docker container by stopping then starting it.

        ``docker.restart`` was removed from the Unraid API 4.32+ schema,
        so this tool composes the restart client-side as a stop → start
        sequence and returns both underlying mutation responses.

        **Partial-failure semantics:** if the stop succeeds but the
        subsequent start fails, the container is left stopped and the
        tool raises an error noting that the stop already completed —
        the operator should call ``unraid_start_container`` to roll
        forward. If the stop itself fails there is no partial state to
        report and the underlying error propagates unchanged.

        Args:
            ctx: FastMCP request context.
            container_id: Container ID.

        Returns:
            ``{"stop": <stop response>, "start": <start response>}`` on
            success, where each value is the raw GraphQL mutation
            response payload for that step.
        """
        client = require_readwrite(ctx, "restart container")
        return await client.restart_container(container_id)

    @unraid_tool(mcp, tags={"write", "docker"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unraid_pause_container(ctx: Context, container_id: str) -> dict[str, Any]:
        """Pause a running Docker container.

        Args:
            ctx: FastMCP request context.
            container_id: Container ID.

        Returns:
            Raw GraphQL mutation response payload.
        """
        client = require_readwrite(ctx, "pause container")
        return await client.pause_container(container_id)

    @unraid_tool(mcp, tags={"write", "docker"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unraid_unpause_container(ctx: Context, container_id: str) -> dict[str, Any]:
        """Unpause a paused Docker container.

        Args:
            ctx: FastMCP request context.
            container_id: Container ID.

        Returns:
            Raw GraphQL mutation response payload.
        """
        client = require_readwrite(ctx, "unpause container")
        return await client.unpause_container(container_id)
