"""FastMCP server creation, lifespan, and mode gating."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from fastmcp import FastMCP
from fastmcp.server.lifespan import Lifespan, lifespan

from unraid_mcp.config import UnraidConfig

logger = logging.getLogger(__name__)


def make_server_lifespan(config: UnraidConfig) -> Lifespan:
    """Build a FastMCP lifespan bound to the given ``UnraidConfig``.

    The lifespan closes over ``config`` so the same config used for mode
    gating in :func:`create_server` is also the one used to initialize the
    Unraid client. This keeps tests and embedded callers from silently
    picking up environment-sourced values when they passed an explicit
    config.

    Yields a plain ``dict[str, Any]`` to match FastMCP's documented
    ``LifespanFn`` contract (see #67). Composed lifespans merge results via
    ``{**left, **right}``, which would ``TypeError`` on a dataclass.
    """

    @lifespan
    async def _server_lifespan(_server: FastMCP) -> AsyncIterator[dict[str, Any]]:  # noqa: PLR0912 — startup flow
        context: dict[str, Any] = {"config": config, "client": None, "init_error": None}

        # Lazily import the client to avoid circular deps at module load time
        from unraid_mcp.clients.unraid import UnraidClient

        if config.unraid_use_https and not config.unraid_verify_ssl:
            logger.warning(
                "TLS verification is DISABLED for %s — UNRAID_VERIFY_SSL=false overrides the "
                "secure default. Acceptable only for self-signed LAN certs on a trusted segment; "
                "an attacker on the network path can capture the API key.",
                config.base_url,
            )

        if config.api_enabled and config.unraid_api_key is not None:
            client = UnraidClient(
                graphql_url=config.graphql_url,
                api_key=config.unraid_api_key,
                verify_ssl=config.unraid_verify_ssl,
                timeout=config.unraid_request_timeout,
                max_retries=config.unraid_max_retries,
            )
            try:
                await client.validate_connection()
            except Exception as exc:
                logger.exception(
                    "Failed to validate Unraid API at %s — tools will return init-failed errors",
                    config.graphql_url,
                )
                context["init_error"] = exc
                await client.close()
            else:
                context["client"] = client
                logger.info("Unraid client initialized and validated")
                # Schema-compatibility probe (#68) — warns on drift but does
                # not fail startup. A failed introspection call itself is
                # logged and ignored so an older server without schema
                # introspection support still boots the MCP server cleanly.
                try:
                    drifts = await client.check_schema_compatibility()
                except Exception:
                    logger.warning(
                        "Schema-compatibility check failed (introspection unavailable?); continuing.",
                        exc_info=True,
                    )
                else:
                    if drifts:
                        for drift in drifts:
                            logger.warning("schema drift: %s", drift)
                        logger.warning(
                            "Detected %d schema-drift issue(s); "
                            "tools reading these fields will fail until queries are updated.",
                            len(drifts),
                        )
                    else:
                        logger.info("Schema compatibility check passed")
        else:
            logger.warning(
                "Unraid API credentials not configured — tools will return "
                "'not configured' errors. See README for required environment variables.",
            )

        try:
            yield context
        finally:
            client = context.get("client")
            if client is not None:
                try:
                    await client.close()
                    logger.info("Closed Unraid client")
                except Exception as close_exc:
                    logger.exception(
                        "Error closing Unraid client (%s)",
                        type(close_exc).__name__,
                    )

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

    # Apply mode gating — hide write tools when the env-flag write-gate is off.
    if not config.enable_write_tools:
        server.disable(tags={"write"})
        logger.info("Read-only mode: write tools disabled")
    else:
        logger.info("Read-write mode: all tools enabled")

    # Secondary gate: user-mutation tools stay hidden unless explicitly allowed
    if not config.unraid_allow_user_mutations:
        server.disable(tags={"user-mutation"})
        logger.info("User-mutation tools disabled (UNRAID_ALLOW_USER_MUTATIONS=false)")

    return server
