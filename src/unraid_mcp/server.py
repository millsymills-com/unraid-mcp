"""FastMCP server creation, lifespan, and mode gating."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from fastmcp import FastMCP
from fastmcp.server.lifespan import Lifespan, lifespan

from unraid_mcp.config import UnraidConfig

logger = logging.getLogger(__name__)


@dataclass
class ServerContext:
    """Lifespan context passed to all tools via ``ctx.lifespan_context``."""

    config: UnraidConfig
    client: object | None = None  # UnraidClient | None — typed loosely to avoid circular imports


def make_server_lifespan(config: UnraidConfig) -> Lifespan:
    """Build a FastMCP lifespan bound to the given ``UnraidConfig``.

    The lifespan closes over ``config`` so the same config used for mode
    gating in :func:`create_server` is also the one used to initialize the
    Unraid client. This keeps tests and embedded callers from silently
    picking up environment-sourced values when they passed an explicit
    config.
    """

    @lifespan  # type: ignore[arg-type]
    async def _server_lifespan(_server: FastMCP) -> AsyncIterator[ServerContext]:
        context = ServerContext(config=config)

        # Lazily import the client to avoid circular deps at module load time
        from unraid_mcp.clients.unraid import UnraidClient

        if config.unraid_use_https and not config.unraid_verify_ssl:
            logger.warning(
                "TLS verification is DISABLED for %s — acceptable for self-signed LAN certs, "
                "but unsafe on untrusted networks. Set UNRAID_VERIFY_SSL=true when possible.",
                config.base_url,
            )

        if config.api_enabled:
            client = UnraidClient(
                graphql_url=config.graphql_url,
                api_key=config.unraid_api_key,  # type: ignore[arg-type]
                verify_ssl=config.unraid_verify_ssl,
                timeout=config.unraid_request_timeout,
                max_retries=config.unraid_max_retries,
            )
            try:
                await client.validate_connection()
            except Exception:
                logger.exception(
                    "Failed to validate Unraid API at %s — tools will return errors",
                    config.graphql_url,
                )
                await client.close()
            else:
                context.client = client
                logger.info("Unraid client initialized and validated")
        else:
            logger.warning("UNRAID_API_KEY not set — tools will return 'not configured' errors")

        try:
            yield context
        finally:
            if context.client is not None:
                try:
                    await context.client.close()  # type: ignore[attr-defined]
                    logger.info("Closed Unraid client")
                except Exception:
                    logger.exception("Error closing Unraid client")

    return _server_lifespan


def create_server(config: UnraidConfig | None = None) -> FastMCP:
    """Create and configure the FastMCP server."""
    if config is None:
        config = UnraidConfig()

    server = FastMCP(
        name="unraid-mcp",
        instructions=(
            "Unraid MCP server providing tools for the Unraid GraphQL API. "
            "Use these tools to query system info, manage the array and parity, "
            "control Docker containers and VMs, browse shares and users, and "
            "review notifications."
        ),
        lifespan=make_server_lifespan(config),
    )

    # Register all tools
    from unraid_mcp.tools import register_all_tools

    register_all_tools(server)

    # Apply mode gating — hide write tools in readonly mode
    if not config.is_readwrite:
        server.disable(tags={"write"})
        logger.info("Read-only mode: write tools disabled")
    else:
        logger.info("Read-write mode: all tools enabled")

    return server
