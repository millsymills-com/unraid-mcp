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


def _emit(message: str) -> None:
    """Write preflight output to stderr; stdout is reserved for stdio JSON-RPC framing."""
    print(message, file=sys.stderr)


def _redact_api_key(key: SecretStr | str | None) -> str:
    """Describe the API key without echoing any of its characters."""
    if key is None:
        return "<not set>"
    raw = key.get_secret_value() if isinstance(key, SecretStr) else key
    if not raw:
        return "<not set>"
    return f"<set, {len(raw)} chars>"


async def _check_schema() -> int:
    """Introspect the live schema and emit a drift report to stderr.

    Exit codes:
        0 — schema matches client expectations
        1 — no API key configured
        2 — drift detected (details emitted to stderr) or connection failure
    """
    config = UnraidConfig()
    if not config.api_enabled:
        _emit("No API key configured — set UNRAID_API_KEY to run the schema check.")
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
            _emit(f"Schema check failed: {type(exc).__name__}: {exc}")
            return 2
        if not drifts:
            _emit(f"Schema compatibility check passed against {config.graphql_url}")
            return 0
        _emit(f"Detected {len(drifts)} schema-drift issue(s):")
        for drift in drifts:
            _emit(f"  • {drift}")
        return 2
    finally:
        await client.close()


async def _check_config() -> int:
    """Emit effective config to stderr and validate connectivity. Returns exit code."""
    config = UnraidConfig()

    _emit("unraid-mcp configuration check")
    _emit(f"  version:         {__version__}")
    _emit(f"  mode:            {config.unraid_mode.value}")
    _emit(f"  endpoint:        {config.graphql_url}")
    _emit(f"  api key:         {_redact_api_key(config.unraid_api_key)}")
    _emit(f"  verify TLS:      {config.unraid_verify_ssl}")
    _emit(f"  request timeout: {config.unraid_request_timeout}s")
    _emit(f"  max retries:     {config.unraid_max_retries}")

    if not config.api_enabled:
        _emit("\nNo API key configured — set UNRAID_API_KEY to run the connectivity check.")
        return 1

    _emit("\nValidating connection…")
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
        _emit(f"  FAIL — {type(exc).__name__}: {exc}")
        return 2
    except Exception as exc:  # defensive: unexpected failure; omit message — could embed the API key
        _emit(f"  FAIL — unexpected {type(exc).__name__}")
        return 2
    else:
        _emit("  OK — server responded to validation query.")
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
