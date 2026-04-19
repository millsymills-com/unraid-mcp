"""Smoke tests against a real Unraid server.

Gated behind the ``integration`` marker so the default ``pytest`` run
skips them. Run with::

    UNRAID_HOST=tower.local UNRAID_API_KEY=... \
        uv run pytest tests/integration/ -m integration

Each test fast-skips when the required env isn't set so contributors
without a live Unraid host aren't blocked.
"""

from __future__ import annotations

import os

import pytest

from unraid_mcp.clients.unraid import UnraidClient

pytestmark = pytest.mark.integration


def _require_env() -> tuple[str, str, bool]:
    api_key = os.environ.get("UNRAID_API_KEY")
    host = os.environ.get("UNRAID_HOST", "tower.local")
    use_https = os.environ.get("UNRAID_USE_HTTPS", "true").lower() != "false"
    if not api_key:
        pytest.skip("set UNRAID_API_KEY (and optionally UNRAID_HOST) to run integration tests")
    return host, api_key, use_https


@pytest.fixture
async def live_client():
    host, api_key, use_https = _require_env()
    scheme = "https" if use_https else "http"
    client = UnraidClient(
        graphql_url=f"{scheme}://{host}/graphql",
        api_key=api_key,
        verify_ssl=os.environ.get("UNRAID_VERIFY_SSL", "false").lower() == "true",
        timeout=15,
        max_retries=1,
    )
    try:
        yield client
    finally:
        await client.close()


async def test_get_info_returns_real_hostname(live_client):
    """Basic round-trip: confirm we reach the server and parse `info.os.hostname`."""
    info = await live_client.get_info()
    assert info.os is not None
    assert info.os.hostname, "Unraid server returned an empty hostname"


async def test_validate_connection_succeeds(live_client):
    """`validate_connection` must not raise against a healthy live server."""
    await live_client.validate_connection()
