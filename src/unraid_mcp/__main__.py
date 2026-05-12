"""Entry point for running unraid-mcp as a module or via the `unraid-mcp` console script."""

from __future__ import annotations

import argparse
import asyncio
import sys

from pydantic import SecretStr

from unraid_mcp import __version__
from unraid_mcp.clients.unraid import UnraidClient
from unraid_mcp.config import UnraidConfig
from unraid_mcp.errors import UnraidError
from unraid_mcp.logging_config import configure_logging
from unraid_mcp.server import create_server


def _redact_api_key(key: SecretStr | str | None) -> str:
    if key is None:
        return "<not set>"
    raw = key.get_secret_value() if isinstance(key, SecretStr) else key
    if not raw:
        return "<not set>"
    if len(raw) <= 8:
        return "***"
    return f"{raw[:4]}…{raw[-2:]}"


async def _check_schema() -> int:
    """Introspect the live schema and print drift report.

    Exit codes:
        0 — schema matches client expectations
        1 — no API key configured
        2 — drift detected (details printed) or connection failure
    """
    config = UnraidConfig()
    if not config.api_enabled:
        print("No API key configured — set UNRAID_API_KEY to run the schema check.")
        return 1

    api_key = config.unraid_api_key
    if api_key is None:  # api_enabled gated this above, kept for type-narrowing
        return 1
    client = UnraidClient(
        graphql_url=config.graphql_url,
        api_key=api_key,
        verify_ssl=config.unraid_verify_ssl,
        timeout=config.unraid_request_timeout,
        max_retries=config.unraid_max_retries,
    )
    try:
        try:
            drifts = await client.check_schema_compatibility()
        except UnraidError as exc:
            print(f"Schema check failed: {type(exc).__name__}: {exc}")
            return 2
        if not drifts:
            print(f"Schema compatibility check passed against {config.graphql_url}")
            return 0
        print(f"Detected {len(drifts)} schema-drift issue(s):")
        for drift in drifts:
            print(f"  • {drift}")
        return 2
    finally:
        await client.close()


async def _check_config() -> int:
    """Print effective config and validate connectivity. Returns exit code."""
    config = UnraidConfig()

    print("unraid-mcp configuration check")
    print(f"  version:         {__version__}")
    print(f"  mode:            {config.unraid_mode.value}")
    print(f"  user mutations:  {'enabled' if config.unraid_allow_user_mutations else 'disabled'}")
    print(f"  endpoint:        {config.graphql_url}")
    print(f"  api key:         {_redact_api_key(config.unraid_api_key)}")
    print(f"  verify TLS:      {config.unraid_verify_ssl}")
    print(f"  request timeout: {config.unraid_request_timeout}s")
    print(f"  max retries:     {config.unraid_max_retries}")

    if not config.api_enabled:
        print("\nNo API key configured — set UNRAID_API_KEY to run the connectivity check.")
        return 1

    print("\nValidating connection…")
    api_key = config.unraid_api_key
    if api_key is None:  # api_enabled gated this above, kept for type-narrowing
        return 1
    client = UnraidClient(
        graphql_url=config.graphql_url,
        api_key=api_key,
        verify_ssl=config.unraid_verify_ssl,
        timeout=config.unraid_request_timeout,
        max_retries=config.unraid_max_retries,
    )
    try:
        await client.validate_connection()
    except UnraidError as exc:
        print(f"  FAIL — {type(exc).__name__}: {exc}")
        return 2
    except Exception as exc:  # defensive: unexpected non-typed failure
        print(f"  FAIL — unexpected {type(exc).__name__}: {exc}")
        return 2
    else:
        print("  OK — server responded to validation query.")
        return 0
    finally:
        await client.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="unraid-mcp",
        description="Production-grade MCP server for the Unraid GraphQL API.",
    )
    parser.add_argument("--version", action="version", version=f"unraid-mcp {__version__}")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help=(
            "Print the resolved configuration, run a single validate_connection "
            "against the Unraid API, and exit without starting the MCP server. "
            "Exit 0 on success, 1 when no API key is configured, 2 on validation failure."
        ),
    )
    parser.add_argument(
        "--check-schema",
        action="store_true",
        help=(
            "Introspect the live Unraid GraphQL schema and report any drift "
            "from what this client expects to query. Exit 0 when the schema "
            "is compatible, 1 when no API key is configured, 2 on drift or "
            "connection failure. Run this against a new Unraid release to "
            "check upgrade compatibility before shipping."
        ),
    )
    return parser


def main() -> None:
    """Start the Unraid MCP server (or run a preflight check)."""
    configure_logging()
    args = _build_parser().parse_args()
    if args.check_config:
        sys.exit(asyncio.run(_check_config()))
    if args.check_schema:
        sys.exit(asyncio.run(_check_schema()))
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
