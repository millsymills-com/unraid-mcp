"""Shared guards for client-layer tests."""

from __future__ import annotations

import logging

import httpx._utils
import pytest

from unraid_mcp.clients.base import _REDACTED_LOGGER_NAMES, _ApiKeyRedactingFilter


@pytest.fixture(autouse=True)
def _stub_system_proxy_lookup(monkeypatch):
    """Stop httpx's per-construction system-proxy probe from hitting macOS ``_scproxy``.

    Every ``httpx.AsyncClient`` build calls ``getproxies()``; on macOS that
    routes into ``getproxies_macosx_sysconf`` (the SystemConfiguration C
    framework), which segfaults under repeated invocation in a long-lived
    runner. A real server builds the client once, but these tests — and
    especially mutmut, which re-runs the suite in-process for every mutant —
    build thousands. ``httpx._utils`` binds ``getproxies`` at import (``from
    urllib.request import getproxies``), so the stub must target that name, not
    ``urllib.request``. Keeps the harness stable without touching production
    proxy behaviour.
    """
    monkeypatch.setattr(httpx._utils, "getproxies", dict)


@pytest.fixture(autouse=True)
def _no_redaction_filter_leak():
    """Fail any test that leaves a client's API-key redaction filter attached.

    ``BaseGraphQLClient`` attaches an :class:`_ApiKeyRedactingFilter` to the
    global httpx/httpcore loggers in ``__init__`` and only detaches it in
    ``close()``. A fixture that builds a client but never closes it therefore
    leaks one filter per test onto process-global loggers — unbounded growth
    that, under a long-lived runner (e.g. mutmut re-running the suite in-process
    for every mutant), accumulates until the interpreter segfaults. This guard
    turns that silent leak into an immediate, local failure.
    """
    yield
    leaked = {
        name: sum(isinstance(f, _ApiKeyRedactingFilter) for f in logging.getLogger(name).filters)
        for name in _REDACTED_LOGGER_NAMES
    }
    offenders = {name: count for name, count in leaked.items() if count}
    assert not offenders, f"client left API-key redaction filters on global loggers (unclosed client?): {offenders}"
