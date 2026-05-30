"""Pure, fixture-free guards for the live-write safety gate.

Kept separate from ``conftest.py`` so offline unit tests can import and exercise
the gate logic without importing the conftest module — importing the conftest
registers its session-scoped autouse fixtures and would skip the whole run.
"""

from __future__ import annotations

import os

import pytest

MCPTEST_PREFIX = "mcptest"


def assert_mcptest(name: str | None) -> None:
    """Hard guard — never operate on a non-``mcptest`` asset."""
    if not name or not str(name).lower().startswith(MCPTEST_PREFIX):
        raise RuntimeError(f"refusing to mutate asset {name!r} — name must start with {MCPTEST_PREFIX!r} for safety")


def require_writes_enabled() -> None:
    """Skip unless live writes are explicitly enabled and an API key is present.

    Loads ``.env`` directly rather than depending on the function-scoped
    ``live_env`` fixture so the session-scoped ``live_mcp_client`` can construct
    ``UnraidConfig`` with env vars visible before the per-test
    ``_isolate_unraid_env`` autouse runs.
    """
    from tests.conftest import load_unraid_env_into_os_environ

    load_unraid_env_into_os_environ()
    if os.environ.get("UNRAID_ALLOW_LIVE_WRITES") != "1":
        pytest.skip(
            "tests/live_write/ is gated. Set UNRAID_ALLOW_LIVE_WRITES=1 to enable "
            "(writes against your live Unraid server using mcptest_* assets)."
        )
    if not os.environ.get("UNRAID_API_KEY"):
        pytest.skip("set UNRAID_API_KEY to run live_write tests")
