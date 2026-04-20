"""Top-level unit-test fixtures.

The project root contains a developer ``.env`` with real credentials. Unit
tests should never pick that up — they use ``monkeypatch`` to set specific
env vars and expect those alone to determine config. But pydantic-settings
reads ``.env`` in addition to the environment, which defeats
``monkeypatch.delenv("UNRAID_API_KEY")`` and causes tests to silently hit
the live server.

This autouse fixture points ``UnraidConfig``'s ``env_file`` to ``None`` for
every test so only explicit env vars (via monkeypatch or fixtures) drive
the config.
"""

from __future__ import annotations

import pytest

from unraid_mcp.config import UnraidConfig


@pytest.fixture(autouse=True)
def _isolate_from_project_dot_env(monkeypatch):
    """Prevent tests from inheriting the developer's ./.env file."""
    monkeypatch.setitem(UnraidConfig.model_config, "env_file", None)
