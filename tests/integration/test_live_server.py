"""Smoke tests against a real Unraid server.

Gated behind the ``integration`` marker so the default ``pytest`` run
skips them. Run with::

    UNRAID_HOST=tower.local UNRAID_API_KEY=... \
        uv run pytest tests/integration/ -m integration

Each test fast-skips when the required env isn't set so contributors
without a live Unraid host aren't blocked.

These exercise only **read** endpoints. Write operations (array stop,
container restart, user create, etc.) are intentionally untested
here — live-testing those needs an opt-in flag so a CI run can't
accidentally bounce someone's array.
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


# ── Lifecycle ──────────────────────────────────────────────────────────


async def test_validate_connection_succeeds(live_client):
    """`validate_connection` must not raise against a healthy live server."""
    await live_client.validate_connection()


# ── System ─────────────────────────────────────────────────────────────


async def test_get_info_returns_real_hostname(live_client):
    """Basic round-trip: confirm we reach the server and parse `info.os.hostname`."""
    info = await live_client.get_info()
    assert info.os is not None
    assert info.os.hostname, "Unraid server returned an empty hostname"


async def test_get_flash_returns_guid(live_client):
    """Every Unraid server has a flash drive with a GUID."""
    flash = await live_client.get_flash()
    assert isinstance(flash, dict)
    assert flash.get("guid"), f"flash.guid missing or empty: {flash}"


async def test_get_registration_returns_state(live_client):
    """Registration info should at minimum expose a state field."""
    registration = await live_client.get_registration()
    assert isinstance(registration, dict)
    assert "state" in registration, f"registration missing 'state': {registration}"


# ── Array + parity ─────────────────────────────────────────────────────


async def test_get_array_returns_state(live_client):
    """Array state is always set (STARTED / STOPPED / STOPPED_UNMOUNTED / etc.)."""
    array = await live_client.get_array()
    assert array.state, f"array.state missing: {array.model_dump(exclude_none=True)}"


async def test_get_parity_history_returns_list(live_client):
    """Parity history is a list — possibly empty on a fresh install, but must be the right type."""
    history = await live_client.get_parity_history()
    assert isinstance(history, list)


# ── Disks ──────────────────────────────────────────────────────────────


async def test_list_disks_returns_non_empty_list(live_client):
    """A real Unraid server has at least the flash disk."""
    disks = await live_client.list_disks()
    assert isinstance(disks, list)
    assert len(disks) >= 1, "expected at least one disk (flash drive)"
    assert any(d.id for d in disks), "no disk has an id"


# ── Docker ─────────────────────────────────────────────────────────────


async def test_list_containers_returns_list(live_client):
    """Possibly empty (fresh install) but must be a list of DockerContainer."""
    containers = await live_client.list_containers()
    assert isinstance(containers, list)


async def test_list_docker_networks_includes_bridge(live_client):
    """Every Docker install has a `bridge` network by default."""
    networks = await live_client.list_docker_networks()
    assert isinstance(networks, list)
    names = {n.name for n in networks if n.name}
    assert "bridge" in names, f"expected 'bridge' network, got {names}"


# ── VMs ────────────────────────────────────────────────────────────────


async def test_list_vms_returns_vms_model(live_client):
    """`vms.domain` is a list — possibly empty if no VMs are defined."""
    vms = await live_client.list_vms()
    # `domain` can be None when libvirt isn't running; we just want the
    # model to parse without raising.
    if vms.domain is not None:
        assert isinstance(vms.domain, list)


# ── Shares ─────────────────────────────────────────────────────────────


async def test_list_shares_includes_any_share(live_client):
    """Most servers have at least one user share."""
    shares = await live_client.list_shares()
    assert isinstance(shares, list)
    # A brand-new server may have zero shares; be lenient, but if any
    # exist at least one should have a name.
    if shares:
        assert any(s.name for s in shares), f"no share has a name: {shares}"


# ── Users ──────────────────────────────────────────────────────────────


async def test_list_users_includes_root(live_client):
    """`root` is always present on an Unraid server."""
    users = await live_client.list_users()
    assert isinstance(users, list)
    names = {u.name for u in users if u.name}
    assert "root" in names, f"expected 'root' user, got {names}"


# ── Notifications ──────────────────────────────────────────────────────


async def test_list_notifications_returns_list(live_client):
    """Notifications list is always present, possibly empty."""
    notifications = await live_client.list_notifications()
    assert isinstance(notifications, list)
