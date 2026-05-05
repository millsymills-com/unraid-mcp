"""Shared test fixtures for unraid-mcp."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

_UNRAID_ENV_PREFIX = "UNRAID_"


@pytest.fixture(autouse=True)
def _isolate_unraid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every `UNRAID_*` env var for the duration of one test.

    Pydantic-settings reads from the process environment at instantiation,
    so an `~/Desktop/Projects/.env`-loaded `UNRAID_API_KEY` would otherwise
    leak into unit tests that explicitly call `monkeypatch.delenv`.
    Autouse + monkeypatch ensures perfect per-test isolation with no
    boilerplate at the call site.

    Also neutralises the `env_file` config on `UnraidConfig` so the
    project-local `.env` file doesn't get read back in by pydantic-settings.
    """
    from unraid_mcp.config import UnraidConfig

    for name in list(os.environ):
        if name.startswith(_UNRAID_ENV_PREFIX):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(UnraidConfig.model_config, "env_file", None)


@pytest.fixture
def live_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Restore `UNRAID_*` env vars from the real process environment.

    Live test suites (`integration/`, `live_write/`, `contract/`) use this
    fixture to opt out of `_isolate_unraid_env`'s stripping. Loads `.env`
    files via python-dotenv first so contributors can keep credentials in
    `~/Desktop/Projects/.env` and the project-local `.env`.
    """
    from pathlib import Path

    from dotenv import dotenv_values

    for envfile in (Path.home() / "Desktop/Projects/.env", Path(".env")):
        if envfile.exists():
            for key, value in dotenv_values(envfile).items():
                if key and key.startswith(_UNRAID_ENV_PREFIX) and value is not None:
                    monkeypatch.setenv(key, value)
    # Anything already exported in the shell wins over .env (matches
    # the precedence the production server uses).
    yield  # noqa: PT022 -- yield-shape reserved for future teardown
