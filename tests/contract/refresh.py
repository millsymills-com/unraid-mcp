"""Refresh the pinned GraphQL schema snapshot from the live Unraid server.

One-shot script: introspects the configured Unraid GraphQL endpoint, dumps the
SDL to ``tests/contract/snapshot.graphql``, and writes the SHA-256 of the SDL
bytes to ``tests/contract/snapshot.sha256``.

Run after intentional schema changes to re-pin the contract::

    set -a; source ~/Desktop/Projects/.env; set +a
    uv run python -m tests.contract.refresh

The introspection request is read-only and safe against a live server.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from graphql import build_client_schema, get_introspection_query, print_schema

from unraid_mcp.clients.unraid import UnraidClient
from unraid_mcp.config import UnraidConfig

if TYPE_CHECKING:
    from graphql.utilities.get_introspection_query import IntrospectionQuery

logger = logging.getLogger(__name__)

_SNAPSHOT_DIR = Path(__file__).parent
_SNAPSHOT_SDL = _SNAPSHOT_DIR / "snapshot.graphql"
_SNAPSHOT_SHA = _SNAPSHOT_DIR / "snapshot.sha256"


async def main() -> int:
    """Fetch the live schema, render SDL, and write the snapshot pair.

    Returns the process exit code: 0 on success, 1 when the API is not
    configured, 2 when introspection or rendering fails.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    config = UnraidConfig()
    if not config.api_enabled or config.unraid_api_key is None:
        logger.error(
            "Unraid API not configured (UNRAID_API_KEY missing). Source ~/Desktop/Projects/.env before running.",
        )
        return 1

    client = UnraidClient(
        graphql_url=config.graphql_url,
        api_key=config.unraid_api_key,
        verify_ssl=config.unraid_verify_ssl,
        timeout=config.unraid_request_timeout,
        max_retries=config.unraid_max_retries,
    )
    try:
        logger.info("Introspecting %s", config.graphql_url)
        try:
            result = await client.query(get_introspection_query())
        except Exception:
            logger.exception("Introspection failed")
            return 2

        try:
            schema = build_client_schema(cast("IntrospectionQuery", result))
            sdl = print_schema(schema)
        except Exception:
            logger.exception("Failed to build schema or render SDL")
            return 2
    finally:
        await client.close()

    sdl_bytes = sdl.encode("utf-8")
    digest = hashlib.sha256(sdl_bytes).hexdigest()

    _SNAPSHOT_SDL.write_bytes(sdl_bytes)
    _SNAPSHOT_SHA.write_text(f"{digest}\n", encoding="utf-8")

    logger.info("Wrote %s (%d bytes)", _SNAPSHOT_SDL, len(sdl_bytes))
    logger.info("Wrote %s (sha256=%s)", _SNAPSHOT_SHA, digest)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
