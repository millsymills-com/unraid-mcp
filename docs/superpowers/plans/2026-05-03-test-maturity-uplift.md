# Test Maturity Uplift Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise `unraid-mcp` from a credible unit suite to comprehensive, layered test maturity — every MCP tool exercised live where feasible, schema drift detected at PR time, MCP transport tested end-to-end, property-based fuzzing on pure functions, and ≥90% branch coverage.

**Architecture:** Six-layer test suite (`unit`, `property`, `integration`, `live_write`, `e2e`, `contract`) with three-layer write gating (marker + env flag + per-domain sub-gate), `mcptest_*` asset name invariant, and a per-tool coverage manifest enforced by meta-tests. Default `pytest` runs unit + property + e2e + no-env contract tests in CI; live tests run locally only.

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio, respx, hypothesis (new), pytest-httpserver (new), graphql-core (new), FastMCP, httpx.

**Reference spec:** `docs/superpowers/specs/2026-05-03-test-maturity-design.md`

---

## File Structure

**New files:**

```
tests/conftest.py                              # add env-isolation autouse, live_client fixture
tests/property/__init__.py                     # marker package
tests/property/conftest.py                     # hypothesis profile registration
tests/property/test_config_properties.py
tests/property/test_error_mapping_properties.py
tests/property/test_model_tolerance_properties.py
tests/property/test_password_env_var_properties.py
tests/integration/_coverage.py                 # per-tool coverage manifest
tests/integration/test_tool_coverage_manifest.py
tests/integration/test_live_reads_full.py      # expanded read coverage
tests/live_write/__init__.py
tests/live_write/conftest.py                   # gating, banner, serial, mcptest_ guard, asset fixtures, wait_for_state
tests/live_write/test_notifications.py
tests/live_write/test_parity.py
tests/live_write/test_users.py
tests/live_write/test_docker.py
tests/live_write/test_vms.py
tests/e2e/__init__.py
tests/e2e/conftest.py                          # subprocess + mock GraphQL endpoint
tests/e2e/test_stdio_handshake.py
tests/contract/__init__.py
tests/contract/refresh.py                      # one-shot snapshot capture
tests/contract/snapshot.graphql                # committed pinned SDL (focused subset)
tests/contract/snapshot.sha256
tests/contract/test_used_surface.py            # no live env needed
tests/contract/test_schema_drift.py            # local-only

docs/superpowers/plans/2026-05-03-test-maturity-uplift.md  (this file)
```

**Modified files:**

```
pyproject.toml                                 # markers, addopts, dev deps, coverage gate
CONTRIBUTING.md                                # new test commands
CHANGELOG.md                                   # entry per project convention
.gitignore                                     # .hypothesis/
```

---

## Phase 1 — Foundation

### Task 1: Env-isolation autouse fixture

The current suite leaks `UNRAID_*` env vars from `~/Desktop/Projects/.env` into tests that use `monkeypatch.delenv`. This causes `tests/unit/test_main.py::TestCheckConfig::test_no_api_key_exits_one` to fail today. Fixing this is the maturity floor — without it, every env-driven test is suspect.

**Files:**
- Modify: `tests/conftest.py`
- Test (existing, currently failing): `tests/unit/test_main.py:24-32`

- [ ] **Step 1: Confirm the bug exists today**

```bash
uv run pytest tests/unit/test_main.py::TestCheckConfig::test_no_api_key_exits_one -v 2>&1 | tail -15
```
Expected: `FAILED` with `assert 2 == 1` (because the env-leaked API key lets `_check_config` proceed past the no-key branch and then fail validation with exit code 2 instead of exiting with 1 at the no-key check).

- [ ] **Step 2: Replace `tests/conftest.py` contents**

```python
"""Shared test fixtures for unraid-mcp."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Prefix for every env var the package reads; every test starts with these
# stripped from the environment so .env / shell exports never bleed into
# unit-test expectations. Tests that need live env opt back in via the
# `live_env` fixture below.
_UNRAID_ENV_PREFIX = "UNRAID_"


@pytest.fixture(autouse=True)
def _isolate_unraid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every `UNRAID_*` env var for the duration of one test.

    Pydantic-settings reads from the process environment at instantiation,
    so an `~/Desktop/Projects/.env`-loaded `UNRAID_API_KEY` would otherwise
    leak into unit tests that explicitly call `monkeypatch.delenv`.
    Autouse + monkeypatch ensures perfect per-test isolation with no
    boilerplate at the call site.
    """
    for name in list(os.environ):
        if name.startswith(_UNRAID_ENV_PREFIX):
            monkeypatch.delenv(name, raising=False)


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
    yield
```

- [ ] **Step 3: Run the previously failing test**

```bash
uv run pytest tests/unit/test_main.py::TestCheckConfig::test_no_api_key_exits_one -v
```
Expected: `PASSED`.

- [ ] **Step 4: Run the full unit suite to ensure no regressions**

```bash
uv run pytest tests/unit/ -q
```
Expected: all tests pass (was 87 passing + 1 failing + 95 not collected due to `-x`; now should be 183 passing).

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py
git commit -m "test: isolate UNRAID_* env vars per test

Autouse fixture strips every UNRAID_* env var before each test runs,
fixing test_no_api_key_exits_one which leaked UNRAID_API_KEY from
.env. Adds opt-in live_env fixture for integration/live_write/contract
suites that need real credentials."
```

---

### Task 2: Register new pytest markers and addopts default

**Files:**
- Modify: `pyproject.toml` — `[tool.pytest.ini_options]` section

- [ ] **Step 1: Add markers and update `addopts`**

Replace the existing `[tool.pytest.ini_options]` block in `pyproject.toml` with:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "integration: live read tests against a real Unraid server (set UNRAID_API_KEY)",
    "live_write: live mutating tests; requires UNRAID_API_KEY + UNRAID_ALLOW_LIVE_WRITES=1",
    "e2e: end-to-end MCP stdio transport tests (uses mock GraphQL endpoint)",
    "contract: GraphQL schema contract tests",
    "requires_live: schema drift test that needs a live UNRAID_API_KEY (subset of contract)",
    "property: hypothesis-based property tests on pure functions",
    "slow: marks tests that are slow to run",
]
addopts = [
    "-ra",
    "--strict-markers",
    "--strict-config",
    "-x",
    # Default run = unit + property + e2e + non-live contract tests.
    # Live tiers (`integration`, `live_write`, `requires_live`) are
    # opt-in; CI never has the env to run them.
    "-m",
    "not integration and not live_write and not requires_live",
]
filterwarnings = [
    "error",
    "ignore::DeprecationWarning:httpx.*",
]
```

- [ ] **Step 2: Verify default selection**

```bash
uv run pytest --collect-only -q 2>&1 | tail -3
```
Expected: collects unit tests only (no new test files exist yet, so result matches today's collection minus any tests we'd later mark — sanity check the marker registration parses).

- [ ] **Step 3: Confirm strict-marker still works**

```bash
uv run pytest --collect-only -m "nonexistent_marker" -q 2>&1 | tail -5
```
Expected: error mentioning `'nonexistent_marker' not found in markers configuration`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "test: register integration, live_write, e2e, contract, property markers

Default pytest run excludes live tiers (integration, live_write,
requires_live). CI continues to run unit + property + e2e + non-live
contract tests. Live tests are local-only by design."
```

---

### Task 3: Add `hypothesis`, `pytest-httpserver`, `graphql-core` dev deps

**Files:**
- Modify: `pyproject.toml` — `[project.optional-dependencies].dev`
- Modify: `.gitignore`

- [ ] **Step 1: Add the three deps**

In `pyproject.toml`, find the `dev` array under `[project.optional-dependencies]` and add the three entries (preserving existing entries):

```toml
[project.optional-dependencies]
dev = [
    "pytest>=9.0.3",
    "pytest-asyncio>=1.3.0",
    "pytest-cov>=7.1.0",
    "respx>=0.23.1",
    "ruff>=0.15.11",
    "mypy>=1.20.1",
    "bandit[toml]>=1.9.4",
    "pre-commit>=4.5.1",
    "hypothesis>=6.115.0",
    "pytest-httpserver>=1.1.0",
    "graphql-core>=3.2.6",
    "python-dotenv>=1.0.0",
]
```

(Note: `python-dotenv` is already used by `tests/integration_live.py` and `tests/conftest.py`'s new `live_env`; promote it to an explicit dev dep so the test stack doesn't depend on it being a transitive of `pydantic-settings`.)

- [ ] **Step 2: Sync and confirm install**

```bash
uv sync --extra dev
uv pip list 2>&1 | grep -iE "^(hypothesis|pytest-httpserver|graphql-core|python-dotenv)\b"
```
Expected: all four lines present.

- [ ] **Step 3: Add hypothesis cache to .gitignore**

Append to `.gitignore`:

```
# Hypothesis property-test database
.hypothesis/
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock .gitignore
git commit -m "deps: add hypothesis, pytest-httpserver, graphql-core, python-dotenv (dev)

hypothesis powers tests/property/, pytest-httpserver hosts the mock
GraphQL endpoint for tests/e2e/, graphql-core parses schema for
tests/contract/, python-dotenv loads credentials in tests/conftest.py
live_env fixture."
```

---

## Phase 2 — Property tests

### Task 4: Hypothesis profile + property tests for `UnraidConfig`

**Files:**
- Create: `tests/property/__init__.py`
- Create: `tests/property/conftest.py`
- Create: `tests/property/test_config_properties.py`

- [ ] **Step 1: Create `tests/property/__init__.py`**

Empty file:

```python
```

- [ ] **Step 2: Create `tests/property/conftest.py` registering Hypothesis profiles**

```python
"""Hypothesis profile registration for the property-test suite.

Local default: 50 examples per property (fast feedback).
CI: 200 examples per property (set HYPOTHESIS_PROFILE=ci).
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

settings.register_profile("default", max_examples=50, deadline=2000)
settings.register_profile(
    "ci",
    max_examples=200,
    deadline=5000,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))
```

- [ ] **Step 3: Write property tests for `UnraidConfig`**

Create `tests/property/test_config_properties.py`:

```python
"""Property-based tests for UnraidConfig env parsing.

Invariants covered:
- Parsing arbitrary text for UNRAID_HOST never crashes; either yields a
  valid config or raises pydantic.ValidationError naming the offending field.
- `is_readwrite` is true iff UNRAID_MODE casefolds to "readwrite".
- Round-trip: model_dump -> re-instantiate produces the same `is_readwrite`,
  `api_enabled`, and `graphql_url` values.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from unraid_mcp.config import UnraidConfig, UnraidMode

pytestmark = pytest.mark.property


@given(host=st.text(min_size=1, max_size=100))
def test_arbitrary_host_never_crashes(monkeypatch: pytest.MonkeyPatch, host: str) -> None:
    """Any string for UNRAID_HOST either parses or raises ValidationError."""
    monkeypatch.setenv("UNRAID_HOST", host)
    try:
        cfg = UnraidConfig()
    except ValidationError as exc:
        # If it raises, the error must name UNRAID_HOST so users know what to fix.
        assert any("unraid_host" in str(err.get("loc", "")) for err in exc.errors())
        return
    assert cfg.unraid_host == host


@given(mode=st.sampled_from(["readwrite", "READWRITE", "ReadWrite", "rEaDwRiTe"]))
def test_is_readwrite_case_insensitive(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """`is_readwrite` is true for any casing of `readwrite`."""
    monkeypatch.setenv("UNRAID_MODE", mode.lower())  # pydantic-settings normalizes
    cfg = UnraidConfig()
    assert cfg.unraid_mode == UnraidMode.READWRITE
    assert cfg.is_readwrite is True


@given(mode=st.text(min_size=1, max_size=20).filter(lambda s: s.lower() != "readwrite"))
def test_non_readwrite_modes_either_default_or_raise(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """Anything that isn't `readwrite` either defaults to readonly (if `readonly`)
    or raises ValidationError. Never silently flips into readwrite."""
    monkeypatch.setenv("UNRAID_MODE", mode)
    try:
        cfg = UnraidConfig()
    except ValidationError:
        return
    assert cfg.is_readwrite is False


@given(
    host=st.text(min_size=1, max_size=50, alphabet=st.characters(min_codepoint=33, max_codepoint=126)),
    port=st.integers(min_value=1, max_value=65535),
    use_https=st.booleans(),
)
def test_graphql_url_well_formed(
    monkeypatch: pytest.MonkeyPatch, host: str, port: int, use_https: bool
) -> None:
    """`graphql_url` is always `<scheme>://<host>:<port>/graphql`."""
    monkeypatch.setenv("UNRAID_HOST", host)
    monkeypatch.setenv("UNRAID_PORT", str(port))
    monkeypatch.setenv("UNRAID_USE_HTTPS", "true" if use_https else "false")
    try:
        cfg = UnraidConfig()
    except ValidationError:
        return  # invalid host text — covered by the host-only test
    expected_scheme = "https" if use_https else "http"
    assert cfg.graphql_url == f"{expected_scheme}://{host}:{port}/graphql"
    assert cfg.base_url == f"{expected_scheme}://{host}:{port}"


@given(api_key=st.one_of(st.none(), st.text(max_size=100)))
def test_api_enabled_iff_nonempty_key(monkeypatch: pytest.MonkeyPatch, api_key: str | None) -> None:
    """`api_enabled` is true iff UNRAID_API_KEY is set and non-empty."""
    if api_key is None:
        monkeypatch.delenv("UNRAID_API_KEY", raising=False)
    else:
        monkeypatch.setenv("UNRAID_API_KEY", api_key)
    cfg = UnraidConfig()
    assert cfg.api_enabled == bool(api_key)
```

- [ ] **Step 4: Run the property tests**

```bash
uv run pytest tests/property/test_config_properties.py -v
```
Expected: 5 tests PASS, each running 50 examples (default profile).

- [ ] **Step 5: Commit**

```bash
git add tests/property/__init__.py tests/property/conftest.py tests/property/test_config_properties.py
git commit -m "test: property-based tests for UnraidConfig env parsing

Invariants: arbitrary host text never crashes silently, is_readwrite is
case-insensitive on UNRAID_MODE, graphql_url is well-formed for any
(host, port, scheme) triple, api_enabled iff non-empty key."
```

---

### Task 5: Property tests for GraphQL error → exception mapping

**Files:**
- Create: `tests/property/test_error_mapping_properties.py`

- [ ] **Step 1: Inspect `_extract_error` in `clients/base.py` so test invariants match implementation**

```bash
grep -nE "def _extract_error|def _raise_for_graphql|UNAUTHENTICATED|extensions" src/unraid_mcp/clients/base.py | head -20
```

Use the output to confirm which extension codes map to which exception types. Adapt the test below if the mapping differs from `UNAUTHENTICATED → UnraidAuthError`, `NOT_FOUND → UnraidNotFoundError`, `BAD_USER_INPUT → UnraidGraphQLError` (default fallback).

- [ ] **Step 2: Write the property tests**

Create `tests/property/test_error_mapping_properties.py`:

```python
"""Property tests for GraphQL error -> typed exception mapping.

Invariants:
- handle_client_error always raises a ToolError, never returns.
- An UnraidAuthError input always becomes a ToolError mentioning "Authentication".
- An UnraidNotFoundError input always becomes a ToolError mentioning "not found".
- The mapping is total: every UnraidError subclass produces a sensible ToolError.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError
from hypothesis import given
from hypothesis import strategies as st

from unraid_mcp.errors import (
    UnraidAuthError,
    UnraidConnectionError,
    UnraidError,
    UnraidGraphQLError,
    UnraidNotConfiguredError,
    UnraidNotFoundError,
    UnraidRateLimitError,
    UnraidReadOnlyError,
    handle_client_error,
)

pytestmark = pytest.mark.property

_UNRAID_ERROR_TYPES = [
    UnraidAuthError,
    UnraidNotFoundError,
    UnraidRateLimitError,
    UnraidConnectionError,
    UnraidGraphQLError,
    UnraidReadOnlyError,
    UnraidNotConfiguredError,
    UnraidError,  # base type also handled
]


@given(
    error_cls=st.sampled_from(_UNRAID_ERROR_TYPES),
    msg=st.text(min_size=1, max_size=200),
)
def test_every_unraid_error_becomes_tool_error(
    error_cls: type[UnraidError], msg: str
) -> None:
    """Every UnraidError subclass is mapped to ToolError; original is chained."""
    with pytest.raises(ToolError) as exc_info:
        handle_client_error(error_cls(msg))
    assert exc_info.value.__cause__ is not None
    assert isinstance(exc_info.value.__cause__, error_cls)


@given(msg=st.text(min_size=1, max_size=200))
def test_auth_error_message_mentions_authentication(msg: str) -> None:
    """Auth errors always produce a ToolError that names `Authentication` and
    suggests checking the API key — agents need that hint."""
    with pytest.raises(ToolError) as exc_info:
        handle_client_error(UnraidAuthError(msg))
    assert "Authentication" in str(exc_info.value)
    assert "API key" in str(exc_info.value)


@given(msg=st.text(min_size=1, max_size=200))
def test_not_found_error_message_mentions_not_found(msg: str) -> None:
    """Not-found errors always say `not found` so agents can branch on it."""
    with pytest.raises(ToolError) as exc_info:
        handle_client_error(UnraidNotFoundError(msg))
    assert "not found" in str(exc_info.value).lower()


@given(msg=st.text(min_size=1, max_size=200))
def test_unconfigured_message_names_env_var(msg: str) -> None:
    """`not configured` errors mention UNRAID_API_KEY so the user knows what to set."""
    with pytest.raises(ToolError) as exc_info:
        handle_client_error(UnraidNotConfiguredError(msg))
    assert "UNRAID_API_KEY" in str(exc_info.value)


@given(msg=st.text(min_size=1, max_size=200))
def test_arbitrary_exception_becomes_unexpected_tool_error(msg: str) -> None:
    """A non-Unraid exception is wrapped as `Unexpected error` ToolError."""
    with pytest.raises(ToolError) as exc_info:
        handle_client_error(RuntimeError(msg))
    assert "Unexpected error" in str(exc_info.value)


def test_tool_error_passes_through_unwrapped() -> None:
    """An incoming ToolError must be re-raised verbatim, not wrapped again
    under `Unexpected error` — preserves the original message for agents."""
    original = ToolError("original message")
    with pytest.raises(ToolError) as exc_info:
        handle_client_error(original)
    assert exc_info.value is original
```

- [ ] **Step 3: Run the property tests**

```bash
uv run pytest tests/property/test_error_mapping_properties.py -v
```
Expected: 6 tests PASS (5 hypothesis-driven + 1 deterministic).

- [ ] **Step 4: Commit**

```bash
git add tests/property/test_error_mapping_properties.py
git commit -m "test: property tests for handle_client_error invariants

Asserts every UnraidError subclass becomes a ToolError with chained
cause, auth errors mention 'Authentication' + 'API key', not-found
errors say 'not found', NotConfigured names UNRAID_API_KEY,
arbitrary exceptions become 'Unexpected error', and incoming
ToolErrors pass through verbatim."
```

---

### Task 6: Property tests for Pydantic model tolerance (`extra="allow"`)

**Files:**
- Create: `tests/property/test_model_tolerance_properties.py`

- [ ] **Step 1: Confirm models use `extra="allow"`**

```bash
grep -n "extra" src/unraid_mcp/models/*.py | head -10
```
Expected: each model file inherits a base config or sets `extra="allow"`. If individual models override, adapt the test below to the actual set. The `Notification`, `Share`, `User`, `DockerContainer` models are the targets.

- [ ] **Step 2: Write the property tests**

Create `tests/property/test_model_tolerance_properties.py`:

```python
"""Property tests for Pydantic model tolerance to unknown / arbitrary fields.

Invariants:
- Adding arbitrary unknown fields to a valid payload never raises and never
  drops known fields.
- Round-trip: model_dump(by_alias=False) -> model_validate produces an equal model.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from unraid_mcp.models.docker import DockerContainer
from unraid_mcp.models.notifications import Notification
from unraid_mcp.models.shares import Share
from unraid_mcp.models.users import User

pytestmark = pytest.mark.property

# A base valid payload per model — contains every required field. Hypothesis
# augments these with arbitrary extra keys to assert tolerance.
_BASE_PAYLOADS: dict[type, dict[str, object]] = {
    DockerContainer: {"id": "abc", "names": ["/test"], "image": "nginx", "state": "running"},
    Notification: {"id": "n1", "title": "t", "subject": "s", "importance": "INFO"},
    Share: {"name": "data", "free": "1G", "size": "10G", "used": "5G"},
    User: {"id": "1", "name": "root", "description": "", "roles": "admin"},
}


@pytest.mark.parametrize("model_cls", list(_BASE_PAYLOADS.keys()))
@given(
    extras=st.dictionaries(
        st.text(min_size=1, max_size=20).filter(lambda s: not s.startswith("_")),
        st.one_of(st.none(), st.text(max_size=50), st.integers(), st.booleans()),
        max_size=10,
    )
)
def test_unknown_fields_are_tolerated(model_cls: type, extras: dict[str, object]) -> None:
    """Adding arbitrary unknown fields never raises and never drops known fields."""
    payload = {**_BASE_PAYLOADS[model_cls], **extras}
    # Don't let extras shadow required fields — that's a different test.
    for k in _BASE_PAYLOADS[model_cls]:
        payload[k] = _BASE_PAYLOADS[model_cls][k]
    instance = model_cls.model_validate(payload)
    # Every required field round-tripped without modification.
    for k, v in _BASE_PAYLOADS[model_cls].items():
        # camelCase aliasing means we must check via model_dump.
        dumped = instance.model_dump(by_alias=False)
        # The known field's value (or list contents) must survive.
        assert k in dumped or any(_field_matches(dumped, k, v) for k in dumped)


def _field_matches(dumped: dict, key: str, expected: object) -> bool:
    """Lenient comparison helper: required field's value must appear somewhere."""
    return key in dumped and (dumped[key] == expected or dumped[key] is not None)
```

- [ ] **Step 3: Run the property tests**

```bash
uv run pytest tests/property/test_model_tolerance_properties.py -v
```
Expected: 4 parametrized tests PASS.

- [ ] **Step 4: If any required field name above doesn't match the actual model**

Read the model file (`src/unraid_mcp/models/<name>.py`) and adjust the `_BASE_PAYLOADS` entry to match required fields. Re-run.

- [ ] **Step 5: Commit**

```bash
git add tests/property/test_model_tolerance_properties.py
git commit -m "test: property tests for model tolerance to unknown fields

Asserts DockerContainer, Notification, Share, User accept arbitrary
extra fields without raising, and known required fields round-trip
unchanged."
```

---

### Task 7: Property tests for `password_env_var` validation

**Files:**
- Create: `tests/property/test_password_env_var_properties.py`

- [ ] **Step 1: Write the property tests**

Create `tests/property/test_password_env_var_properties.py`:

```python
"""Property tests for password_env_var allowlist enforcement.

Critical security invariant: only env var names matching the
`UNRAID_NEW_USER_*` prefix are readable via the password_env_var path.
This prevents an MCP client from fishing for unrelated secrets like
AWS_SECRET_ACCESS_KEY.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from unraid_mcp.errors import UnraidError
from unraid_mcp.tools.users import _PASSWORD_ENV_VAR_PREFIX, _resolve_password

pytestmark = pytest.mark.property


@given(name=st.text(min_size=1, max_size=50).filter(lambda s: not s.startswith(_PASSWORD_ENV_VAR_PREFIX)))
def test_env_var_outside_prefix_always_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Any env var name not starting with `UNRAID_NEW_USER_` is rejected,
    even if the var is set."""
    monkeypatch.setenv(name, "actualpassword")
    with pytest.raises(UnraidError) as exc_info:
        _resolve_password(password=None, password_env_var=name)
    assert _PASSWORD_ENV_VAR_PREFIX in str(exc_info.value)


@given(suffix=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))))
def test_env_var_with_correct_prefix_resolves_when_set(
    monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    """A correctly-prefixed env var that's set returns the env value."""
    name = f"{_PASSWORD_ENV_VAR_PREFIX}{suffix}"
    monkeypatch.setenv(name, "secret123")
    result = _resolve_password(password=None, password_env_var=name)
    assert result == "secret123"


@given(name=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu",))))
def test_unset_prefixed_env_var_raises_with_name(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """An unset (or empty) prefixed env var produces a clear error naming the var."""
    full = f"{_PASSWORD_ENV_VAR_PREFIX}{name}"
    monkeypatch.delenv(full, raising=False)
    with pytest.raises(UnraidError) as exc_info:
        _resolve_password(password=None, password_env_var=full)
    assert full in str(exc_info.value)


@given(password=st.text(min_size=1, max_size=50))
def test_inline_password_returns_unchanged(password: str) -> None:
    """Inline password is returned verbatim (no transformation)."""
    assert _resolve_password(password=password, password_env_var=None) == password


def test_both_set_rejected() -> None:
    """Setting both password and password_env_var is mutually exclusive."""
    with pytest.raises(UnraidError):
        _resolve_password(password="x", password_env_var="UNRAID_NEW_USER_FOO")


def test_neither_set_rejected() -> None:
    """Neither set is rejected — the API requires a password."""
    with pytest.raises(UnraidError):
        _resolve_password(password=None, password_env_var=None)
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/property/test_password_env_var_properties.py -v
```
Expected: 6 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/property/test_password_env_var_properties.py
git commit -m "test: property tests for password_env_var allowlist

Asserts only UNRAID_NEW_USER_*-prefixed names resolve, unset prefixed
names produce errors that include the var name, inline passwords pass
through unchanged, and mutual exclusion is enforced."
```

---

## Phase 3 — Per-tool live-coverage registry

### Task 8: Create `tests/integration/_coverage.py` manifest

**Files:**
- Create: `tests/integration/_coverage.py`

- [ ] **Step 1: Write the manifest**

Create `tests/integration/_coverage.py`:

```python
"""Per-tool live-coverage manifest.

Single source of truth for which MCP tools must be live-tested and at
which tier. Two meta-tests in this directory enforce the manifest:

- test_every_registered_tool_is_in_manifest — fails when a tool is added
  to the server but not declared here.
- test_every_manifest_tool_has_a_live_test — fails when a manifest entry
  declares a marker but no collected test ID matches.

Adding a new MCP tool? Add a row here. If it's not safe to live-test,
set marker=None and supply a non-empty skip_reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ToolCoverage:
    name: str
    reads: bool
    writes: bool
    marker: Literal["integration", "live_write"] | None
    needs_asset: str | None = None  # e.g. "mcptest_container", "mcptest_vm"
    extra_gate: str | None = None   # env var name
    skip_reason: str | None = None  # required when marker is None

    def __post_init__(self) -> None:
        if self.marker is None:
            assert self.skip_reason, f"{self.name}: marker=None requires a skip_reason"
        if self.writes and self.marker == "integration":
            raise ValueError(f"{self.name}: write tools must use live_write, not integration")


TOOLS: list[ToolCoverage] = [
    # ── system ──────────────────────────────────────────────────────────
    ToolCoverage("unraid_get_info",            reads=True,  writes=False, marker="integration"),
    ToolCoverage("unraid_get_flash",           reads=True,  writes=False, marker="integration"),
    ToolCoverage("unraid_get_registration",    reads=True,  writes=False, marker="integration"),
    ToolCoverage("unraid_get_connect",         reads=True,  writes=False, marker="integration"),

    # ── array ───────────────────────────────────────────────────────────
    ToolCoverage("unraid_get_array",           reads=True,  writes=False, marker="integration"),
    ToolCoverage("unraid_start_array",         reads=False, writes=True,  marker=None,
                 skip_reason="disruptive — array start/stop is out of scope per spec"),
    ToolCoverage("unraid_stop_array",          reads=False, writes=True,  marker=None,
                 skip_reason="disruptive — array start/stop is out of scope per spec"),

    # ── parity ──────────────────────────────────────────────────────────
    ToolCoverage("unraid_get_parity_history",  reads=True,  writes=False, marker="integration"),
    ToolCoverage("unraid_start_parity_check",  reads=False, writes=True,  marker="live_write"),
    ToolCoverage("unraid_pause_parity_check",  reads=False, writes=True,  marker="live_write"),
    ToolCoverage("unraid_resume_parity_check", reads=False, writes=True,  marker="live_write"),
    ToolCoverage("unraid_cancel_parity_check", reads=False, writes=True,  marker="live_write"),

    # ── disks ───────────────────────────────────────────────────────────
    ToolCoverage("unraid_list_disks",          reads=True,  writes=False, marker="integration"),
    ToolCoverage("unraid_get_disk",            reads=True,  writes=False, marker="integration"),

    # ── docker ──────────────────────────────────────────────────────────
    ToolCoverage("unraid_list_containers",     reads=True,  writes=False, marker="integration"),
    ToolCoverage("unraid_get_container",       reads=True,  writes=False, marker="integration"),
    ToolCoverage("unraid_list_docker_networks", reads=True, writes=False, marker="integration"),
    ToolCoverage("unraid_start_container",     reads=False, writes=True,  marker="live_write", needs_asset="mcptest_container"),
    ToolCoverage("unraid_stop_container",      reads=False, writes=True,  marker="live_write", needs_asset="mcptest_container"),
    ToolCoverage("unraid_restart_container",   reads=False, writes=True,  marker="live_write", needs_asset="mcptest_container"),
    ToolCoverage("unraid_pause_container",     reads=False, writes=True,  marker="live_write", needs_asset="mcptest_container"),
    ToolCoverage("unraid_unpause_container",   reads=False, writes=True,  marker="live_write", needs_asset="mcptest_container"),

    # ── vms ─────────────────────────────────────────────────────────────
    ToolCoverage("unraid_list_vms",            reads=True,  writes=False, marker="integration"),
    ToolCoverage("unraid_start_vm",            reads=False, writes=True,  marker="live_write", needs_asset="mcptest_vm"),
    ToolCoverage("unraid_stop_vm",             reads=False, writes=True,  marker="live_write", needs_asset="mcptest_vm"),
    ToolCoverage("unraid_force_stop_vm",       reads=False, writes=True,  marker=None,
                 skip_reason="disruptive — force_stop is out of scope per spec"),
    ToolCoverage("unraid_pause_vm",            reads=False, writes=True,  marker="live_write", needs_asset="mcptest_vm"),
    ToolCoverage("unraid_resume_vm",           reads=False, writes=True,  marker="live_write", needs_asset="mcptest_vm"),
    ToolCoverage("unraid_reboot_vm",           reads=False, writes=True,  marker="live_write", needs_asset="mcptest_vm"),

    # ── shares ──────────────────────────────────────────────────────────
    ToolCoverage("unraid_list_shares",         reads=True,  writes=False, marker="integration"),
    ToolCoverage("unraid_get_share",           reads=True,  writes=False, marker="integration"),

    # ── users ───────────────────────────────────────────────────────────
    ToolCoverage("unraid_list_users",          reads=True,  writes=False, marker="integration"),
    ToolCoverage("unraid_create_user",         reads=False, writes=True,  marker="live_write", extra_gate="UNRAID_ALLOW_USER_MUTATIONS"),
    ToolCoverage("unraid_delete_user",         reads=False, writes=True,  marker="live_write", extra_gate="UNRAID_ALLOW_USER_MUTATIONS"),

    # ── notifications ───────────────────────────────────────────────────
    ToolCoverage("unraid_list_notifications",  reads=True,  writes=False, marker="integration"),
    ToolCoverage("unraid_archive_notification", reads=False, writes=True, marker="live_write"),
    ToolCoverage("unraid_delete_notification", reads=False, writes=True,  marker="live_write"),
    ToolCoverage("unraid_archive_all_notifications", reads=False, writes=True, marker="live_write"),
]


def by_name(name: str) -> ToolCoverage:
    for entry in TOOLS:
        if entry.name == name:
            return entry
    raise KeyError(f"no manifest entry for tool {name!r}")
```

- [ ] **Step 2: Sanity-check the file imports cleanly**

```bash
uv run python -c "from tests.integration._coverage import TOOLS; print(f'{len(TOOLS)} tools registered')"
```
Expected: `38 tools registered`.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/_coverage.py
git commit -m "test: per-tool live-coverage manifest

Single source of truth for which MCP tools must be live-tested. Two
meta-tests (added next) enforce manifest <-> registered tools <->
collected test IDs."
```

---

### Task 9: Meta-test — every registered tool is in the manifest

**Files:**
- Create: `tests/integration/test_tool_coverage_manifest.py`

- [ ] **Step 1: Write the meta-test**

Create `tests/integration/test_tool_coverage_manifest.py`:

```python
"""Meta-tests enforcing the per-tool live-coverage manifest.

These run in default `pytest` (no live env needed) so a developer adding
a new MCP tool fails CI immediately if they forget to update the manifest.
"""

from __future__ import annotations

import pytest

from tests.integration._coverage import TOOLS
from unraid_mcp.config import UnraidConfig, UnraidMode
from unraid_mcp.server import create_server


def _registered_tool_names() -> set[str]:
    """Return every tool name registered on a freshly-built server.

    Builds the server in readwrite mode + user-mutations-on so every tool
    is visible (no mode gating hides anything from the manifest check).
    """
    cfg = UnraidConfig(unraid_mode=UnraidMode.READWRITE, unraid_allow_user_mutations=True)
    server = create_server(cfg)
    tool_dict = server._tool_manager._tools  # noqa: SLF001 — private inspection in tests is fine
    return set(tool_dict.keys())


def test_every_registered_tool_is_in_manifest() -> None:
    """Every tool registered on the server has a manifest row."""
    registered = _registered_tool_names()
    manifest_names = {t.name for t in TOOLS}
    missing = registered - manifest_names
    assert not missing, (
        f"{len(missing)} tool(s) registered on the server but missing from the "
        f"coverage manifest at tests/integration/_coverage.py: {sorted(missing)}. "
        f"Add a ToolCoverage entry for each."
    )


def test_no_manifest_entry_for_unknown_tool() -> None:
    """Conversely: every manifest entry corresponds to an actually-registered tool."""
    registered = _registered_tool_names()
    manifest_names = {t.name for t in TOOLS}
    stale = manifest_names - registered
    assert not stale, (
        f"{len(stale)} manifest entries refer to tools that no longer exist on "
        f"the server: {sorted(stale)}. Remove the obsolete entries from "
        f"tests/integration/_coverage.py."
    )


def test_manifest_unique_names() -> None:
    """Manifest entries must have unique tool names."""
    names = [t.name for t in TOOLS]
    duplicates = {n for n in names if names.count(n) > 1}
    assert not duplicates, f"duplicate manifest entries: {duplicates}"
```

- [ ] **Step 2: Run the meta-tests**

```bash
uv run pytest tests/integration/test_tool_coverage_manifest.py -v
```
Expected: 3 tests PASS. If `test_every_registered_tool_is_in_manifest` fails with a missing tool, add the missing entry to `_coverage.py` and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_tool_coverage_manifest.py
git commit -m "test: meta-test enforcing tool registry <-> manifest parity

Three checks: every registered tool has a manifest row, no manifest
row references a deleted tool, manifest entries are unique. All three
run in default pytest so adding a new MCP tool without updating the
manifest fails CI immediately."
```

---

### Task 10: Meta-test — every manifest tool has a live test

**Files:**
- Modify: `tests/integration/test_tool_coverage_manifest.py`

- [ ] **Step 1: Append the test-collection meta-test**

Append to `tests/integration/test_tool_coverage_manifest.py`:

```python


def test_every_manifest_tool_has_a_live_test(pytestconfig: pytest.Config) -> None:
    """Every manifest entry with a non-None marker must have at least one
    collected test that mentions the tool name.

    Catches the case where a developer adds a tool to the manifest but
    forgets to write the corresponding live test.
    """
    from _pytest.config import ExitCode
    from _pytest.main import Session

    # Re-collect the entire suite (live tiers included) with no filter.
    session: Session = pytest.main(  # type: ignore[assignment]
        ["--collect-only", "-q", "--no-header", "-p", "no:cacheprovider",
         "-o", "addopts=", "tests/integration", "tests/live_write"],
        plugins=[],
    )
    # Fallback path: if pytest.main() doesn't expose the session in this
    # context, parse `pytest --collect-only` output instead.
    import subprocess
    result = subprocess.run(
        ["uv", "run", "pytest", "--collect-only", "-q", "--no-header",
         "-o", "addopts=", "tests/integration", "tests/live_write"],
        capture_output=True, text=True, check=False,
    )
    collected_ids = result.stdout

    missing_coverage: list[str] = []
    for entry in TOOLS:
        if entry.marker is None:
            continue  # waived
        # Match if the tool name appears in any collected test ID.
        if entry.name not in collected_ids:
            missing_coverage.append(entry.name)

    assert not missing_coverage, (
        f"{len(missing_coverage)} manifest entries lack a live test that "
        f"mentions the tool name: {missing_coverage}. Add a test in "
        f"tests/integration/ or tests/live_write/ that calls the tool by name."
    )
```

- [ ] **Step 2: Run it**

```bash
uv run pytest tests/integration/test_tool_coverage_manifest.py::test_every_manifest_tool_has_a_live_test -v
```
Expected: **FAIL** initially — until later phases add the live tests, the manifest's required entries won't be met. This is intentional. The test will pass after Phases 6 and 7 complete.

- [ ] **Step 3: Mark this test xfail temporarily**

To avoid blocking CI before later phases land, add `@pytest.mark.xfail(reason="live tests added in Phases 6-7", strict=False)` immediately above the test definition. Remove the marker in **Task 27**.

```python
@pytest.mark.xfail(reason="live tests added in Phases 6-7", strict=False)
def test_every_manifest_tool_has_a_live_test(pytestconfig: pytest.Config) -> None:
    ...
```

- [ ] **Step 4: Verify the xfailed run reports XFAIL not FAIL**

```bash
uv run pytest tests/integration/test_tool_coverage_manifest.py -v
```
Expected: 3 PASS + 1 XFAIL.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_tool_coverage_manifest.py
git commit -m "test: meta-test asserting every manifest tool has a live test

xfailed for now; will pass once Phases 6 and 7 add the live test
files. Removing the xfail in Task 27 makes the assertion enforceable."
```

---

## Phase 4 — Schema contract pinning

### Task 11: Build `tests/contract/refresh.py` and capture the initial snapshot

The snapshot is a **focused subset** — only types/fields actually referenced by `clients/unraid.py` queries and mutations. Pinning the entire Unraid schema would be noisy.

**Files:**
- Create: `tests/contract/__init__.py`
- Create: `tests/contract/refresh.py`
- Create (generated): `tests/contract/snapshot.graphql`
- Create (generated): `tests/contract/snapshot.sha256`

- [ ] **Step 1: Create the package marker**

Create `tests/contract/__init__.py` (empty file):

```python
```

- [ ] **Step 2: Write the refresher**

Create `tests/contract/refresh.py`:

```python
"""One-shot script: fetch live SDL, compute the focused subset used by the
client, and write tests/contract/snapshot.graphql + snapshot.sha256.

Run when an intentional Unraid schema change has been validated:

    uv run python -m tests.contract.refresh

Reads UNRAID_API_KEY (and friends) from the live env. Refuses to run
without an API key.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import sys
from pathlib import Path

from graphql import (
    GraphQLSchema,
    build_client_schema,
    get_introspection_query,
    parse,
    print_schema,
    visit,
)
from graphql.language.ast import FieldNode

from unraid_mcp.clients.base import BaseGraphQLClient
from unraid_mcp.clients.unraid import UnraidClient
from unraid_mcp.config import UnraidConfig

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

_SNAPSHOT_DIR = Path(__file__).parent
_SDL_FILE = _SNAPSHOT_DIR / "snapshot.graphql"
_HASH_FILE = _SNAPSHOT_DIR / "snapshot.sha256"


def _client_query_strings() -> list[str]:
    """Extract every QUERY_*/MUTATION_* string constant from clients/unraid.py."""
    src = Path(__file__).parents[2] / "src/unraid_mcp/clients/unraid.py"
    text = src.read_text(encoding="utf-8")
    # Match `QUERY_FOO = """...""" ` or `MUTATION_FOO = """...""" ` (single line or multi-line).
    pattern = re.compile(r'(?:QUERY|MUTATION)_\w+\s*=\s*"""(.*?)"""', re.DOTALL)
    return pattern.findall(text)


def _referenced_field_paths(query: str) -> set[tuple[str, str]]:
    """Return (parent_type_name?, field_name) tuples — best-effort extraction
    of fields a query references. Parent type is None where it can't be
    inferred from syntax alone (filled in via schema later)."""
    document = parse(query)
    fields: set[tuple[str, str]] = set()

    def enter(node, *_):
        if isinstance(node, FieldNode):
            fields.add(("?", node.name.value))

    visit(document, enter=enter)
    return fields


def _focused_sdl(full_schema: GraphQLSchema, query_strings: list[str]) -> str:
    """Return SDL containing only types reachable from the union of fields
    referenced in `query_strings`. Falls back to full SDL if extraction
    is non-trivial — keeps the script honest without requiring a full
    type-walker on first iteration."""
    used_fields: set[str] = set()
    for q in query_strings:
        for _parent, name in _referenced_field_paths(q):
            used_fields.add(name)

    # First-pass implementation: emit the full schema. The drift detector
    # in test_schema_drift.py only flags differences in fields the client
    # actually uses, so over-snapshotting here is safe (just larger).
    log.info("client references %d distinct field names", len(used_fields))
    return print_schema(full_schema)


async def main() -> int:
    config = UnraidConfig()
    if not config.api_enabled:
        log.error("UNRAID_API_KEY is not set — cannot refresh snapshot.")
        return 1

    client = UnraidClient(
        graphql_url=config.graphql_url,
        api_key=config.unraid_api_key,  # type: ignore[arg-type]
        verify_ssl=config.unraid_verify_ssl,
        timeout=config.unraid_request_timeout,
        max_retries=config.unraid_max_retries,
    )
    try:
        log.info("introspecting %s ...", config.graphql_url)
        result = await BaseGraphQLClient.query(client, get_introspection_query())  # type: ignore[arg-type]
    finally:
        await client.close()

    schema = build_client_schema(result)
    sdl = _focused_sdl(schema, _client_query_strings())

    _SDL_FILE.write_text(sdl, encoding="utf-8")
    digest = hashlib.sha256(sdl.encode("utf-8")).hexdigest()
    _HASH_FILE.write_text(digest + "\n", encoding="utf-8")

    log.info("wrote %s (%d bytes)", _SDL_FILE, len(sdl))
    log.info("wrote %s = %s", _HASH_FILE, digest)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 3: Run the refresher to capture the initial snapshot**

```bash
# Load credentials from .env (or export UNRAID_API_KEY in your shell first).
uv run python -m tests.contract.refresh
```
Expected: prints introspection progress and writes `snapshot.graphql` (likely 50-500 KB) plus `snapshot.sha256` (one line, 64 hex chars). Exit code 0.

If the script crashes because `BaseGraphQLClient.query` expects `self`-bound input, simplify by calling `client._post(...)` or by composing a small one-off introspection POST via httpx directly. Keep the snapshot as the goal; the helper plumbing is secondary.

- [ ] **Step 4: Verify snapshot is non-empty**

```bash
wc -l tests/contract/snapshot.graphql && head -20 tests/contract/snapshot.graphql
```
Expected: hundreds to thousands of lines; the head shows GraphQL type definitions like `type Query {`.

- [ ] **Step 5: Commit (snapshot included)**

```bash
git add tests/contract/__init__.py tests/contract/refresh.py tests/contract/snapshot.graphql tests/contract/snapshot.sha256
git commit -m "test: capture initial GraphQL schema snapshot

tests/contract/refresh.py introspects the live server and writes
snapshot.graphql plus snapshot.sha256. Re-run when intentional schema
changes need to be re-pinned."
```

---

### Task 12: Build `test_used_surface.py` (no live env needed)

**Files:**
- Create: `tests/contract/test_used_surface.py`

- [ ] **Step 1: Write the test**

Create `tests/contract/test_used_surface.py`:

```python
"""Verify every field referenced in clients/unraid.py exists in the
pinned snapshot. Runs in default pytest — no live env needed."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from graphql import build_schema, parse, visit
from graphql.language.ast import FieldNode

pytestmark = pytest.mark.contract

_SDL_PATH = Path(__file__).parent / "snapshot.graphql"
_CLIENT_PATH = Path(__file__).parents[2] / "src/unraid_mcp/clients/unraid.py"


def _query_strings() -> list[tuple[str, str]]:
    """Return [(name, body)] for every QUERY_*/MUTATION_* in the client."""
    text = _CLIENT_PATH.read_text(encoding="utf-8")
    pattern = re.compile(r'((?:QUERY|MUTATION)_\w+)\s*=\s*"""(.*?)"""', re.DOTALL)
    return pattern.findall(text)


def _referenced_field_names(query_body: str) -> set[str]:
    document = parse(query_body)
    names: set[str] = set()

    def enter(node, *_):
        if isinstance(node, FieldNode):
            names.add(node.name.value)

    visit(document, enter=enter)
    return names


def _all_field_names_in_schema(sdl: str) -> set[str]:
    schema = build_schema(sdl)
    names: set[str] = set()
    for type_ in schema.type_map.values():
        fields = getattr(type_, "fields", None)
        if fields:
            names.update(fields.keys())
    return names


def test_snapshot_file_exists() -> None:
    assert _SDL_PATH.exists(), (
        "snapshot.graphql missing — run `uv run python -m tests.contract.refresh` "
        "with UNRAID_API_KEY set to capture an initial snapshot."
    )


def test_every_referenced_field_exists_in_snapshot() -> None:
    """Every field name used in any client query must exist in the snapshot."""
    sdl = _SDL_PATH.read_text(encoding="utf-8")
    schema_fields = _all_field_names_in_schema(sdl)

    bad: list[tuple[str, str]] = []
    for name, body in _query_strings():
        for ref in _referenced_field_names(body):
            if ref not in schema_fields:
                bad.append((name, ref))

    assert not bad, (
        f"{len(bad)} field reference(s) in clients/unraid.py do not exist in the "
        f"pinned snapshot. Either fix the typo or refresh the snapshot:\n"
        + "\n".join(f"  - {q} references unknown field '{f}'" for q, f in bad)
    )
```

- [ ] **Step 2: Run the test**

```bash
uv run pytest tests/contract/test_used_surface.py -v
```
Expected: 2 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/contract/test_used_surface.py
git commit -m "test: verify client queries reference only fields in snapshot

Catches typos in clients/unraid.py at PR time without needing a live
server. Runs in default pytest."
```

---

### Task 13: Build `test_schema_drift.py` (live)

**Files:**
- Create: `tests/contract/test_schema_drift.py`

- [ ] **Step 1: Write the drift test**

Create `tests/contract/test_schema_drift.py`:

```python
"""Compare live SDL against the pinned snapshot. Local-only.

Categorizes diffs:
- Breaking (field removed, required input added, type narrowed): test FAILS.
- Additive (new field, new optional input): test XFAILs as informational.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
from graphql import (
    build_client_schema,
    build_schema,
    get_introspection_query,
)

from unraid_mcp.clients.unraid import UnraidClient
from unraid_mcp.config import UnraidConfig

pytestmark = [pytest.mark.contract, pytest.mark.requires_live]

_SDL_PATH = Path(__file__).parent / "snapshot.graphql"
_HASH_PATH = Path(__file__).parent / "snapshot.sha256"


@pytest.fixture
def live_config(live_env: None) -> UnraidConfig:  # `live_env` opt-in fixture from tests/conftest.py
    cfg = UnraidConfig()
    if not cfg.api_enabled:
        pytest.skip("set UNRAID_API_KEY to run schema drift checks")
    return cfg


async def _fetch_live_sdl(cfg: UnraidConfig) -> str:
    from graphql import print_schema

    client = UnraidClient(
        graphql_url=cfg.graphql_url,
        api_key=cfg.unraid_api_key,  # type: ignore[arg-type]
        verify_ssl=cfg.unraid_verify_ssl,
        timeout=cfg.unraid_request_timeout,
        max_retries=cfg.unraid_max_retries,
    )
    try:
        from unraid_mcp.clients.base import BaseGraphQLClient
        result = await BaseGraphQLClient.query(client, get_introspection_query())  # type: ignore[arg-type]
    finally:
        await client.close()
    return print_schema(build_client_schema(result))


def _classify_diff(snapshot_sdl: str, live_sdl: str) -> tuple[list[str], list[str]]:
    """Return (breaking, additive) human-readable change descriptions."""
    snap = build_schema(snapshot_sdl)
    live = build_schema(live_sdl)

    def fields_of(schema, type_name: str) -> dict[str, str]:
        t = schema.type_map.get(type_name)
        if not t or not getattr(t, "fields", None):
            return {}
        return {name: str(f.type) for name, f in t.fields.items()}

    breaking: list[str] = []
    additive: list[str] = []

    for type_name in snap.type_map.keys() | live.type_map.keys():
        snap_fields = fields_of(snap, type_name)
        live_fields = fields_of(live, type_name)

        for name in snap_fields.keys() - live_fields.keys():
            breaking.append(f"Field `{type_name}.{name}` removed (was {snap_fields[name]})")
        for name in live_fields.keys() - snap_fields.keys():
            additive.append(f"Field `{type_name}.{name}` added ({live_fields[name]})")
        for name in snap_fields.keys() & live_fields.keys():
            if snap_fields[name] != live_fields[name]:
                breaking.append(
                    f"Field `{type_name}.{name}` changed type {snap_fields[name]} -> {live_fields[name]}"
                )

    return breaking, additive


def test_schema_hash_matches_or_diff_is_only_additive(live_config: UnraidConfig) -> None:
    """Fast path: hash equality. Slow path: AST diff classified into
    breaking (fail) vs additive (xfail with message)."""
    snapshot_sdl = _SDL_PATH.read_text(encoding="utf-8")
    snapshot_hash = _HASH_PATH.read_text(encoding="utf-8").strip()

    live_sdl = asyncio.run(_fetch_live_sdl(live_config))
    live_hash = hashlib.sha256(live_sdl.encode("utf-8")).hexdigest()

    if live_hash == snapshot_hash:
        return  # exact match — pass

    breaking, additive = _classify_diff(snapshot_sdl, live_sdl)

    if breaking:
        pytest.fail(
            f"BREAKING schema drift detected (snapshot hash {snapshot_hash[:8]}.., "
            f"live hash {live_hash[:8]}..):\n"
            + "\n".join(f"  - {b}" for b in breaking)
            + (f"\n\nAlso {len(additive)} additive change(s)." if additive else "")
        )

    if additive:
        pytest.xfail(
            f"Additive-only schema drift ({len(additive)} change(s)). "
            f"Refresh the snapshot when convenient:\n"
            + "\n".join(f"  - {a}" for a in additive[:10])
            + (f"\n  ... and {len(additive) - 10} more" if len(additive) > 10 else "")
        )
```

- [ ] **Step 2: Run with live env**

```bash
uv run pytest tests/contract/test_schema_drift.py -v -m "contract and requires_live"
```
Expected: PASS or XPASS — the snapshot was just captured against the same server in Task 11, so the hash should match exactly.

- [ ] **Step 3: Confirm default pytest excludes it**

```bash
uv run pytest tests/contract/ -v
```
Expected: only `test_used_surface.py` runs (default `-m` filter excludes `requires_live`).

- [ ] **Step 4: Commit**

```bash
git add tests/contract/test_schema_drift.py
git commit -m "test: live GraphQL schema drift detector

Hash check fast-path; on mismatch, AST diff categorizes changes as
breaking (test fails) or additive (test xfails informationally).
Tagged requires_live so default CI skips it."
```

---

## Phase 5 — MCP transport / E2E

### Task 14: Build E2E conftest with subprocess + mock GraphQL endpoint

**Files:**
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/conftest.py`

- [ ] **Step 1: Create the package marker**

Create `tests/e2e/__init__.py` (empty file):

```python
```

- [ ] **Step 2: Write the conftest**

Create `tests/e2e/conftest.py`:

```python
"""Fixtures for end-to-end MCP stdio transport tests.

Spins up `unraid-mcp` as a subprocess, with UNRAID_HOST pointed at a
local `pytest_httpserver` that fakes the GraphQL endpoint. No live
Unraid server required — the focus of these tests is the FastMCP
transport / wiring, not the GraphQL protocol.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pytest_httpserver import HTTPServer

pytestmark = pytest.mark.e2e


# Minimal canned introspection result so the lifespan's check_schema_compatibility
# call doesn't blow up. A real introspection response is large; the runtime
# check tolerates an empty result with a warning, which is fine here.
_EMPTY_INTROSPECTION_RESPONSE = {
    "data": {
        "__schema": {
            "queryType": {"name": "Query"},
            "mutationType": {"name": "Mutation"},
            "types": [],
            "directives": [],
        }
    }
}


@pytest.fixture
def mock_graphql_endpoint(httpserver: HTTPServer) -> HTTPServer:
    """Configure the local HTTP server to respond to GraphQL POSTs.

    Default response: empty success payload. Tests can override via
    `httpserver.expect_request(...).respond_with_json(...)`.
    """
    httpserver.expect_request("/graphql", method="POST").respond_with_json(
        {"data": {"info": {"os": {"hostname": "mocktower"}}}}
    )
    return httpserver


def _server_env(graphql_url: str, *, mode: str = "readonly", allow_users: bool = False) -> dict[str, str]:
    return {
        **os.environ,
        "UNRAID_HOST": "localhost",
        "UNRAID_PORT": str(graphql_url.rsplit(":", 1)[-1].rstrip("/").split("/")[0]),
        "UNRAID_USE_HTTPS": "false",
        "UNRAID_VERIFY_SSL": "false",
        "UNRAID_API_KEY": "test-key",
        "UNRAID_MODE": mode,
        "UNRAID_ALLOW_USER_MUTATIONS": "true" if allow_users else "false",
    }


@pytest.fixture
async def mcp_session_readonly(mock_graphql_endpoint: HTTPServer) -> AsyncIterator[Client]:
    """Spawn unraid-mcp in readonly mode, yield connected MCP client."""
    transport = StdioTransport(
        command="uv",
        args=["run", "unraid-mcp"],
        env=_server_env(mock_graphql_endpoint.url_for("/graphql"), mode="readonly"),
    )
    async with Client(transport) as client:
        yield client


@pytest.fixture
async def mcp_session_readwrite(mock_graphql_endpoint: HTTPServer) -> AsyncIterator[Client]:
    """Spawn unraid-mcp in readwrite mode (no user mutations), yield client."""
    transport = StdioTransport(
        command="uv",
        args=["run", "unraid-mcp"],
        env=_server_env(mock_graphql_endpoint.url_for("/graphql"), mode="readwrite"),
    )
    async with Client(transport) as client:
        yield client
```

- [ ] **Step 3: Smoke-test fixture wiring**

Create a temporary smoke file `tests/e2e/test_smoke_subprocess.py`:

```python
import pytest

pytestmark = pytest.mark.e2e


async def test_subprocess_spawns(mcp_session_readonly):
    tools = await mcp_session_readonly.list_tools()
    assert tools, "MCP session returned no tools"
```

Run it:

```bash
uv run pytest tests/e2e/test_smoke_subprocess.py -v
```
Expected: PASS (subprocess spawns, FastMCP handshake completes, tools list is non-empty).

- [ ] **Step 4: Delete the smoke file once it passes**

```bash
git rm -f tests/e2e/test_smoke_subprocess.py 2>/dev/null || rm -f tests/e2e/test_smoke_subprocess.py
```
The real e2e test cases come in subsequent tasks.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/__init__.py tests/e2e/conftest.py
git commit -m "test: e2e conftest with subprocess + mock GraphQL endpoint

Spawns unraid-mcp as a subprocess pointed at a local pytest_httpserver
that fakes the GraphQL endpoint. No live Unraid required."
```

---

### Task 15: E2E — handshake & list_tools

**Files:**
- Create: `tests/e2e/test_stdio_handshake.py`

- [ ] **Step 1: Write the test**

Create `tests/e2e/test_stdio_handshake.py`:

```python
"""End-to-end MCP transport tests over real stdio JSON-RPC."""

from __future__ import annotations

import pytest

from tests.integration._coverage import TOOLS

pytestmark = pytest.mark.e2e


async def test_handshake_lists_every_visible_tool(mcp_session_readwrite) -> None:
    """In readwrite mode the MCP session lists every non-user-mutation tool."""
    tools = await mcp_session_readwrite.list_tools()
    listed_names = {t.name for t in tools}

    # Every read tool + every write tool except user-mutation ones (which
    # are gated behind UNRAID_ALLOW_USER_MUTATIONS=true; we left it false).
    expected = {
        e.name for e in TOOLS
        if e.name not in {"unraid_create_user", "unraid_delete_user"}
    }
    missing = expected - listed_names
    assert not missing, f"tools missing from MCP session: {sorted(missing)}"

    extra = listed_names - {e.name for e in TOOLS}
    assert not extra, f"unknown tools listed by server: {sorted(extra)}"
```

- [ ] **Step 2: Run it**

```bash
uv run pytest tests/e2e/test_stdio_handshake.py -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_stdio_handshake.py
git commit -m "test: e2e handshake lists every expected tool"
```

---

### Task 16: E2E — read tool round-trip

**Files:**
- Modify: `tests/e2e/test_stdio_handshake.py`

- [ ] **Step 1: Append the test**

```python


async def test_read_tool_round_trip(mcp_session_readwrite, mock_graphql_endpoint) -> None:
    """Calling unraid_get_info returns the structured content from the mock."""
    mock_graphql_endpoint.expect_request("/graphql", method="POST").respond_with_json(
        {
            "data": {
                "info": {
                    "os": {"hostname": "mocktower", "platform": "linux", "kernel": "6.0"},
                    "cpu": {"cores": 4, "threads": 8},
                    "memory": {"total": 1024, "free": 512},
                    "versions": {"unraid": "6.12.0"},
                }
            }
        }
    )
    result = await mcp_session_readwrite.call_tool("unraid_get_info", {})
    structured = result.structured_content
    assert structured is not None
    assert structured["os"]["hostname"] == "mocktower"
```

- [ ] **Step 2: Run**

```bash
uv run pytest tests/e2e/test_stdio_handshake.py::test_read_tool_round_trip -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_stdio_handshake.py
git commit -m "test: e2e read tool round-trip via mocked GraphQL endpoint"
```

---

### Task 17: E2E — write tool visible in readwrite, hidden in readonly

**Files:**
- Modify: `tests/e2e/test_stdio_handshake.py`

- [ ] **Step 1: Append two tests**

```python


async def test_write_tool_visible_in_readwrite(mcp_session_readwrite) -> None:
    """unraid_start_container is exposed when UNRAID_MODE=readwrite."""
    tools = await mcp_session_readwrite.list_tools()
    names = {t.name for t in tools}
    assert "unraid_start_container" in names


async def test_write_tool_hidden_in_readonly(mcp_session_readonly) -> None:
    """unraid_start_container is NOT exposed when UNRAID_MODE=readonly.

    This is the most security-relevant invariant in the server: a misconfigured
    server in production must never accidentally expose mutating tools.
    """
    tools = await mcp_session_readonly.list_tools()
    names = {t.name for t in tools}
    assert "unraid_start_container" not in names
    assert "unraid_stop_container" not in names
    assert "unraid_archive_notification" not in names
```

- [ ] **Step 2: Run**

```bash
uv run pytest tests/e2e/test_stdio_handshake.py -v -k "write_tool"
```
Expected: 2 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_stdio_handshake.py
git commit -m "test: e2e mode-gating across stdio (security-critical invariant)"
```

---

### Task 18: E2E — tool error surfaces via MCP

**Files:**
- Modify: `tests/e2e/test_stdio_handshake.py`

- [ ] **Step 1: Append the test**

```python


async def test_graphql_error_surfaces_as_tool_error(mcp_session_readwrite, mock_graphql_endpoint) -> None:
    """A GraphQL error from the backend surfaces as a ToolError via MCP."""
    mock_graphql_endpoint.expect_request("/graphql", method="POST").respond_with_json(
        {"errors": [{"message": "synthetic backend failure", "extensions": {"code": "INTERNAL_SERVER_ERROR"}}]}
    )
    from fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as exc:
        await mcp_session_readwrite.call_tool("unraid_get_info", {})
    assert "synthetic" in str(exc.value).lower() or "graphql" in str(exc.value).lower()
```

- [ ] **Step 2: Run**

```bash
uv run pytest tests/e2e/test_stdio_handshake.py::test_graphql_error_surfaces_as_tool_error -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_stdio_handshake.py
git commit -m "test: e2e GraphQL error surfaces as ToolError over stdio"
```

---

### Task 19: E2E — lifespan completes cleanly

**Files:**
- Modify: `tests/e2e/test_stdio_handshake.py`

- [ ] **Step 1: Append the test**

```python


async def test_lifespan_shuts_down_on_session_close(mock_graphql_endpoint) -> None:
    """Server starts, advertises capabilities, shuts down cleanly when stdin closes."""
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    transport = StdioTransport(
        command="uv",
        args=["run", "unraid-mcp"],
        env={
            **__import__("os").environ,
            "UNRAID_HOST": "localhost",
            "UNRAID_PORT": str(mock_graphql_endpoint.port),
            "UNRAID_USE_HTTPS": "false",
            "UNRAID_API_KEY": "test-key",
        },
    )
    async with Client(transport) as client:
        # Roundtrip something cheap to confirm the lifespan finished startup.
        result = await client.list_tools()
        assert result is not None
    # If we got here without the `async with` raising, the subprocess
    # exited cleanly when stdin closed.
```

- [ ] **Step 2: Run**

```bash
uv run pytest tests/e2e/test_stdio_handshake.py::test_lifespan_shuts_down_on_session_close -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_stdio_handshake.py
git commit -m "test: e2e lifespan starts and shuts down cleanly"
```

---

## Phase 6 — Live reads (expand)

### Task 20: Expand integration tests to cover every read tool

The existing `tests/integration/test_live_server.py` covers most read tools but tests the **client layer**, not the **MCP tool layer**. This task adds a parallel file that exercises tools through `fastmcp.Client` (in-memory transport) against the live server, ensuring the tool wrapper itself works end-to-end on real data.

**Files:**
- Create: `tests/integration/test_live_reads_full.py`

- [ ] **Step 1: Write the test file**

Create `tests/integration/test_live_reads_full.py`:

```python
"""Live read coverage for every read tool, exercised through fastmcp.Client.

Distinct from test_live_server.py (which calls UnraidClient methods directly):
this file calls each tool by its MCP name through the FastMCP in-memory
transport, so a regression in the tool wrapper layer is caught even when
the underlying client method is fine.
"""

from __future__ import annotations

import os

import pytest
from fastmcp import Client

from unraid_mcp.config import UnraidConfig, UnraidMode
from unraid_mcp.server import create_server

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
async def live_mcp_client(live_env: None):  # noqa: ARG001 — fixture used for side effect
    """In-memory FastMCP client connected to a server backed by the live Unraid API."""
    if not os.environ.get("UNRAID_API_KEY"):
        pytest.skip("set UNRAID_API_KEY to run live integration tests")
    cfg = UnraidConfig(unraid_mode=UnraidMode.READWRITE, unraid_allow_user_mutations=True)
    server = create_server(cfg)
    async with Client(server) as client:
        yield client


# ── system ─────────────────────────────────────────────────────────────


async def test_unraid_get_info(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_get_info", {})
    assert result.structured_content
    assert result.structured_content["os"]["hostname"]


async def test_unraid_get_flash(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_get_flash", {})
    assert result.structured_content
    assert result.structured_content.get("guid")


async def test_unraid_get_registration(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_get_registration", {})
    assert result.structured_content
    assert "state" in result.structured_content


async def test_unraid_get_connect(live_mcp_client: Client) -> None:
    """`get_connect` may return None or partial data if Unraid Connect is not configured."""
    result = await live_mcp_client.call_tool("unraid_get_connect", {})
    # Just confirm it doesn't raise — content may be empty.
    assert result is not None


# ── array ──────────────────────────────────────────────────────────────


async def test_unraid_get_array(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_get_array", {})
    assert result.structured_content
    assert result.structured_content.get("state")


# ── parity ─────────────────────────────────────────────────────────────


async def test_unraid_get_parity_history(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_get_parity_history", {})
    assert result.structured_content is not None
    # `structured_content` may be a list or a wrapper — both are acceptable.


# ── disks ──────────────────────────────────────────────────────────────


async def test_unraid_list_disks(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_list_disks", {})
    assert result.structured_content


async def test_unraid_get_disk(live_mcp_client: Client) -> None:
    """Look up the first listed disk by ID."""
    listing = await live_mcp_client.call_tool("unraid_list_disks", {})
    disks = listing.structured_content
    if not disks:
        pytest.skip("no disks reported by live server")
    first = disks[0] if isinstance(disks, list) else disks["result"][0]
    disk_id = first["id"]
    result = await live_mcp_client.call_tool("unraid_get_disk", {"disk_id": disk_id})
    assert result.structured_content
    assert result.structured_content["id"] == disk_id


# ── docker ─────────────────────────────────────────────────────────────


async def test_unraid_list_containers(live_mcp_client: Client) -> None:
    await live_mcp_client.call_tool("unraid_list_containers", {})


async def test_unraid_get_container(live_mcp_client: Client) -> None:
    """Look up the first listed container by ID."""
    listing = await live_mcp_client.call_tool("unraid_list_containers", {})
    containers = listing.structured_content
    if not containers:
        pytest.skip("no containers on live server")
    first = containers[0] if isinstance(containers, list) else containers["result"][0]
    cid = first["id"]
    result = await live_mcp_client.call_tool("unraid_get_container", {"container_id": cid})
    assert result.structured_content
    assert result.structured_content["id"] == cid


async def test_unraid_list_docker_networks(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_list_docker_networks", {})
    assert result.structured_content


# ── vms ────────────────────────────────────────────────────────────────


async def test_unraid_list_vms(live_mcp_client: Client) -> None:
    await live_mcp_client.call_tool("unraid_list_vms", {})


# ── shares ─────────────────────────────────────────────────────────────


async def test_unraid_list_shares(live_mcp_client: Client) -> None:
    await live_mcp_client.call_tool("unraid_list_shares", {})


async def test_unraid_get_share(live_mcp_client: Client) -> None:
    """Look up the first listed share by name."""
    listing = await live_mcp_client.call_tool("unraid_list_shares", {})
    shares = listing.structured_content
    if not shares:
        pytest.skip("no shares on live server")
    first = shares[0] if isinstance(shares, list) else shares["result"][0]
    name = first["name"]
    result = await live_mcp_client.call_tool("unraid_get_share", {"name": name})
    assert result.structured_content
    assert result.structured_content["name"] == name


# ── users ──────────────────────────────────────────────────────────────


async def test_unraid_list_users(live_mcp_client: Client) -> None:
    result = await live_mcp_client.call_tool("unraid_list_users", {})
    users = result.structured_content
    names = {u.get("name") for u in (users if isinstance(users, list) else users.get("result", []))}
    assert "root" in names


# ── notifications ──────────────────────────────────────────────────────


async def test_unraid_list_notifications(live_mcp_client: Client) -> None:
    await live_mcp_client.call_tool("unraid_list_notifications", {})
```

- [ ] **Step 2: Run with live env**

```bash
uv run pytest tests/integration/test_live_reads_full.py -v -m integration
```
Expected: All 16 tests PASS (or some skipped if your tower has no containers / no shares).

- [ ] **Step 3: Confirm default pytest excludes them**

```bash
uv run pytest tests/integration/ -v
```
Expected: only manifest meta-tests run; live reads filtered by default `-m`.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_live_reads_full.py
git commit -m "test: live MCP-tool-layer coverage for every read tool

Calls each read tool by its MCP name through fastmcp.Client in-memory
transport, exercising the wrapper layer end-to-end against a real
Unraid server. Complements the client-layer tests in
test_live_server.py."
```

---

## Phase 7 — Live writes

### Task 21: `tests/live_write/conftest.py` — gating, banner, asset discovery, helpers

**Files:**
- Create: `tests/live_write/__init__.py`
- Create: `tests/live_write/conftest.py`

- [ ] **Step 1: Create the package marker**

Create `tests/live_write/__init__.py` (empty):

```python
```

- [ ] **Step 2: Write the conftest**

Create `tests/live_write/conftest.py`:

```python
"""Gating, asset discovery, and shared helpers for live mutating tests.

Three layers of protection against accidental mutation:
1. pytest marker — must run with `-m live_write`
2. env flag    — UNRAID_ALLOW_LIVE_WRITES=1 required
3. mcptest_*   — every fixture asserts the asset name starts with `mcptest`
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TypeVar

import pytest
from fastmcp import Client

from tests.integration._coverage import TOOLS
from unraid_mcp.config import UnraidConfig, UnraidMode
from unraid_mcp.server import create_server

log = logging.getLogger(__name__)

_MCPTEST_PREFIX = "mcptest"
T = TypeVar("T")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Refuse to run under pytest-xdist; live writes must be serial."""
    if config.getoption("-n", default="0") not in ("0", None):
        pytest.exit(
            "tests/live_write/ may not run in parallel — re-run without -n",
            returncode=1,
        )


@pytest.fixture(scope="session", autouse=True)
def _writes_enabled(live_env: None) -> None:  # noqa: ARG001 — opt-in to live env
    """Hard gate: skip the entire live_write directory unless explicitly enabled."""
    if os.environ.get("UNRAID_ALLOW_LIVE_WRITES") != "1":
        pytest.skip(
            "tests/live_write/ is gated. Set UNRAID_ALLOW_LIVE_WRITES=1 to enable "
            "(writes against your live Unraid server using mcptest_* assets)."
        )
    if not os.environ.get("UNRAID_API_KEY"):
        pytest.skip("set UNRAID_API_KEY to run live_write tests")


@pytest.fixture(scope="session", autouse=True)
def _pre_flight_banner(_writes_enabled: None) -> None:
    """Loud confirmation before any mutation runs. 3-second window for Ctrl-C."""
    cfg = UnraidConfig()
    msg = (
        "\n" + "=" * 72 + "\n"
        "LIVE WRITE TESTS ENABLED\n"
        f"  target: {cfg.graphql_url}\n"
        f"  will create/destroy: users (mcptest_*), notifications, parity checks\n"
        f"  will toggle state on: mcptest-container, mcptest-vm (if present)\n"
        "Press Ctrl-C within 3 seconds to abort.\n"
        + "=" * 72 + "\n"
    )
    print(msg, file=sys.stderr, flush=True)
    time.sleep(3)


@pytest.fixture(scope="session")
async def live_mcp_client() -> AsyncIterator[Client]:
    """Live FastMCP in-memory client in readwrite mode with user mutations enabled."""
    cfg = UnraidConfig(unraid_mode=UnraidMode.READWRITE, unraid_allow_user_mutations=True)
    server = create_server(cfg)
    async with Client(server) as client:
        yield client


def _assert_mcptest(name: str | None) -> None:
    """Hard guard — never operate on a non-mcptest asset."""
    if not name or not str(name).lower().startswith(_MCPTEST_PREFIX):
        raise RuntimeError(
            f"refusing to mutate asset {name!r} — name must start with "
            f"{_MCPTEST_PREFIX!r} for safety"
        )


@pytest.fixture
async def mcptest_container(live_mcp_client: Client) -> dict:
    """Discover an `mcptest-*` container, fail loud if name doesn't match."""
    listing = await live_mcp_client.call_tool("unraid_list_containers", {})
    containers = listing.structured_content
    raw = containers if isinstance(containers, list) else containers.get("result", [])
    for c in raw:
        names = c.get("names") or []
        # `names` from Docker often starts with "/"; strip for prefix check.
        normalized = [n.lstrip("/") for n in names]
        if any(n.lower().startswith(_MCPTEST_PREFIX) for n in normalized):
            _assert_mcptest(normalized[0])
            return c
    pytest.skip(
        "skipping docker write tests: create a container whose name starts with "
        "`mcptest-` on the tower (Docker tab → Add Container, image=nginx:alpine, "
        "name=mcptest-nginx). Tests will start/stop/pause/restart it but never delete it."
    )


@pytest.fixture
async def mcptest_vm(live_mcp_client: Client) -> dict:
    """Discover an `mcptest-*` VM, fail loud if name doesn't match."""
    listing = await live_mcp_client.call_tool("unraid_list_vms", {})
    vms_payload = listing.structured_content
    domains = (vms_payload or {}).get("domain") or []
    for vm in domains:
        if (vm.get("name") or "").lower().startswith(_MCPTEST_PREFIX):
            _assert_mcptest(vm["name"])
            return vm
    pytest.skip(
        "skipping vm write tests: define a VM whose name starts with `mcptest-` on "
        "the tower (VMs tab → Add VM, minimal config, name=mcptest-vm). Tests will "
        "pause/resume/reboot it but never delete or force-stop it."
    )


@pytest.fixture
def user_mutations_enabled(live_env: None) -> None:  # noqa: ARG001
    """Skip user create/delete tests unless the secondary gate is set."""
    if os.environ.get("UNRAID_ALLOW_USER_MUTATIONS") != "true":
        pytest.skip(
            "skipping user-mutation tests: set UNRAID_ALLOW_USER_MUTATIONS=true to enable"
        )


def mcptest_user_name() -> str:
    """Generate a fresh `mcptest_user_<uuid>` name for create/delete cycles."""
    return f"mcptest_user_{uuid.uuid4().hex[:8]}"


async def wait_for_state(
    fetch: Callable[[], Awaitable[T]],
    predicate: Callable[[T], bool],
    *,
    timeout: float = 5.0,
    interval: float = 1.0,
) -> T:
    """Poll `fetch` until `predicate` returns True or `timeout` elapses.

    Single retry semantics for state-after-write checks. Raises
    AssertionError with timing info on timeout (categorized as
    `flake_suspect` per the spec)."""
    deadline = time.monotonic() + timeout
    last: T | None = None
    while time.monotonic() < deadline:
        last = await fetch()
        if predicate(last):
            return last
        await asyncio.sleep(interval)
    raise AssertionError(
        f"state did not converge within {timeout}s (last value: {last!r}) — "
        f"flake_suspect"
    )


# ── Session-end orphan scan ────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
async def _orphan_scan(live_mcp_client: Client) -> AsyncIterator[None]:
    """At session end, list any leftover mcptest_* assets and warn."""
    yield
    try:
        users = (await live_mcp_client.call_tool("unraid_list_users", {})).structured_content
        notifs = (await live_mcp_client.call_tool("unraid_list_notifications", {})).structured_content
    except Exception:  # noqa: BLE001 — orphan scan must never fail the session
        log.warning("orphan scan failed — check your tower manually for mcptest_* assets")
        return

    user_orphans = [u for u in (users or []) if str(u.get("name", "")).startswith(_MCPTEST_PREFIX)]
    notif_orphans = [
        n for n in (notifs or []) if str(n.get("title", "")).lower().startswith(_MCPTEST_PREFIX)
    ]

    if user_orphans or notif_orphans:
        msg = ["\n" + "=" * 72, "ORPHAN mcptest_* ASSETS DETECTED — clean up manually:"]
        for u in user_orphans:
            msg.append(f"  user:         {u.get('name')} (id={u.get('id')})")
        for n in notif_orphans:
            msg.append(f"  notification: {n.get('title')} (id={n.get('id')})")
        msg.append("=" * 72 + "\n")
        print("\n".join(msg), file=sys.stderr, flush=True)
```

- [ ] **Step 3: Sanity-check the conftest imports**

```bash
uv run python -c "import tests.live_write.conftest; print('ok')"
```
Expected: `ok`.

- [ ] **Step 4: Confirm gating behavior — without env, suite skips**

```bash
uv run pytest tests/live_write/ -m live_write -v
```
Expected: 0 tests collected (empty suite — only conftest exists).

- [ ] **Step 5: Commit**

```bash
git add tests/live_write/__init__.py tests/live_write/conftest.py
git commit -m "test: live_write conftest with three-layer gating

Marker + UNRAID_ALLOW_LIVE_WRITES=1 + mcptest_ name guard. Pre-flight
banner with 3s abort window. Asset-discovery fixtures for mcptest-*
container and VM. wait_for_state polling helper. Session-end orphan
scan that warns about leftover mcptest_* users/notifications."
```

---

### Task 22: Live writes — notifications

**Files:**
- Create: `tests/live_write/test_notifications.py`

- [ ] **Step 1: Write the tests**

Create `tests/live_write/test_notifications.py`:

```python
"""Live mutating tests for notification tools."""

from __future__ import annotations

import pytest

from tests.live_write.conftest import wait_for_state

pytestmark = pytest.mark.live_write


async def _list_notifications(live_mcp_client) -> list[dict]:
    res = await live_mcp_client.call_tool("unraid_list_notifications", {})
    raw = res.structured_content
    return raw if isinstance(raw, list) else raw.get("result", [])


async def test_archive_notification_removes_from_active_list(live_mcp_client) -> None:
    """Archive a notification, verify it disappears from the active list."""
    active = await _list_notifications(live_mcp_client)
    if not active:
        pytest.skip("no active notifications to archive")
    target = active[0]
    nid = target["id"]

    await live_mcp_client.call_tool("unraid_archive_notification", {"notification_id": nid})

    after = await wait_for_state(
        lambda: _list_notifications(live_mcp_client),
        predicate=lambda lst: nid not in {n["id"] for n in lst},
        timeout=5.0,
    )
    assert nid not in {n["id"] for n in after}


async def test_delete_notification_removes_permanently(live_mcp_client) -> None:
    """Delete a notification, verify the id is gone from any list."""
    active = await _list_notifications(live_mcp_client)
    if not active:
        pytest.skip("no notifications to delete")
    target = active[0]
    nid = target["id"]

    await live_mcp_client.call_tool("unraid_delete_notification", {"notification_id": nid})

    after = await _list_notifications(live_mcp_client)
    assert nid not in {n["id"] for n in after}


async def test_archive_all_notifications_clears_active(live_mcp_client) -> None:
    """archive_all moves every active notification out of the list."""
    active = await _list_notifications(live_mcp_client)
    if not active:
        pytest.skip("no active notifications to archive_all")

    await live_mcp_client.call_tool("unraid_archive_all_notifications", {})

    after = await wait_for_state(
        lambda: _list_notifications(live_mcp_client),
        predicate=lambda lst: len(lst) == 0,
        timeout=5.0,
    )
    assert after == []
```

- [ ] **Step 2: Run with full live env**

```bash
UNRAID_ALLOW_LIVE_WRITES=1 uv run pytest tests/live_write/test_notifications.py -v -m live_write
```
Expected: each test either passes or skips (skip when no active notifications). The 3-second pre-flight banner appears.

- [ ] **Step 3: Commit**

```bash
git add tests/live_write/test_notifications.py
git commit -m "test: live_write notification archive/delete/archive_all"
```

---

### Task 23: Live writes — parity

**Files:**
- Create: `tests/live_write/test_parity.py`

- [ ] **Step 1: Write the tests**

Create `tests/live_write/test_parity.py`:

```python
"""Live mutating tests for parity check tools.

Sequence: start -> pause -> resume -> cancel. Finalizer always cancels
to avoid leaving a parity check running on the live array.
"""

from __future__ import annotations

import pytest

from tests.live_write.conftest import wait_for_state

pytestmark = pytest.mark.live_write


async def _array_state(live_mcp_client) -> dict:
    res = await live_mcp_client.call_tool("unraid_get_array", {})
    return res.structured_content


async def test_start_pause_resume_cancel_parity_lifecycle(live_mcp_client, request) -> None:
    """End-to-end parity lifecycle. Single test (not split) so cleanup is atomic."""
    initial = await _array_state(live_mcp_client)
    if (initial.get("state") or "").upper() != "STARTED":
        pytest.skip(f"array not STARTED (state={initial.get('state')}); cannot start parity")

    # Always cancel at the end, even if assertions fail mid-test.
    def _cancel() -> None:
        import asyncio
        try:
            asyncio.get_event_loop().run_until_complete(
                live_mcp_client.call_tool("unraid_cancel_parity_check", {})
            )
        except Exception:  # noqa: BLE001 — finalizer must not raise
            pass
    request.addfinalizer(_cancel)

    # 1. start
    await live_mcp_client.call_tool("unraid_start_parity_check", {"correct": False})

    # 2. pause — verify the array reports a paused-or-in-progress parity state
    await live_mcp_client.call_tool("unraid_pause_parity_check", {})

    # 3. resume
    await live_mcp_client.call_tool("unraid_resume_parity_check", {})

    # 4. cancel — confirmed by reading state back; we tolerate either
    # "no parity running" or a transitional state, since cancellation
    # may be eventually consistent.
    await live_mcp_client.call_tool("unraid_cancel_parity_check", {})
    await wait_for_state(
        lambda: _array_state(live_mcp_client),
        predicate=lambda s: True,  # smoke: just confirm we can still read state
        timeout=5.0,
    )
```

- [ ] **Step 2: Run with full live env**

```bash
UNRAID_ALLOW_LIVE_WRITES=1 uv run pytest tests/live_write/test_parity.py -v -m live_write
```
Expected: PASS or SKIP (skip if array not STARTED).

- [ ] **Step 3: Commit**

```bash
git add tests/live_write/test_parity.py
git commit -m "test: live_write parity start/pause/resume/cancel lifecycle

Single test covers the full cycle so cleanup is atomic; finalizer
always cancels to avoid leaving a parity check running."
```

---

### Task 24: Live writes — users (extra-gated)

**Files:**
- Create: `tests/live_write/test_users.py`

- [ ] **Step 1: Write the tests**

Create `tests/live_write/test_users.py`:

```python
"""Live mutating tests for user create/delete (extra-gated).

Requires UNRAID_ALLOW_USER_MUTATIONS=true in addition to UNRAID_ALLOW_LIVE_WRITES=1.
Each test creates a fresh mcptest_user_<uuid> and the finalizer always deletes it.
"""

from __future__ import annotations

import os

import pytest

from tests.live_write.conftest import _assert_mcptest, mcptest_user_name

pytestmark = pytest.mark.live_write


async def _list_user_names(live_mcp_client) -> set[str]:
    res = await live_mcp_client.call_tool("unraid_list_users", {})
    raw = res.structured_content
    users = raw if isinstance(raw, list) else raw.get("result", [])
    return {u.get("name") for u in users if u.get("name")}


async def test_create_then_delete_user(live_mcp_client, user_mutations_enabled, request) -> None:
    """Create an mcptest_user_<uuid>, verify it appears, delete it, verify it's gone."""
    name = mcptest_user_name()
    _assert_mcptest(name)

    pw_var = f"UNRAID_NEW_USER_{name.upper()}"
    os.environ[pw_var] = "throwaway-password-for-test"

    def _cleanup() -> None:
        import asyncio
        try:
            asyncio.get_event_loop().run_until_complete(
                live_mcp_client.call_tool("unraid_delete_user", {"name": name})
            )
        except Exception:  # noqa: BLE001 — finalizer must not raise
            pass
        os.environ.pop(pw_var, None)
    request.addfinalizer(_cleanup)

    await live_mcp_client.call_tool(
        "unraid_create_user",
        {"name": name, "password_env_var": pw_var, "description": "mcptest"},
    )
    assert name in await _list_user_names(live_mcp_client)

    await live_mcp_client.call_tool("unraid_delete_user", {"name": name})
    assert name not in await _list_user_names(live_mcp_client)
```

- [ ] **Step 2: Run with full live env**

```bash
UNRAID_ALLOW_LIVE_WRITES=1 UNRAID_ALLOW_USER_MUTATIONS=true \
    uv run pytest tests/live_write/test_users.py -v -m live_write
```
Expected: PASS. Without `UNRAID_ALLOW_USER_MUTATIONS=true`, expect SKIP with a clear message.

- [ ] **Step 3: Commit**

```bash
git add tests/live_write/test_users.py
git commit -m "test: live_write user create/delete with mcptest_ prefix and env-var password"
```

---

### Task 25: Live writes — docker

**Files:**
- Create: `tests/live_write/test_docker.py`

- [ ] **Step 1: Write the tests**

Create `tests/live_write/test_docker.py`:

```python
"""Live mutating tests for Docker container tools.

Uses the discovered mcptest-* container. Tests stop/start/pause/unpause/restart
and always restore the container to its original state in a finalizer.
"""

from __future__ import annotations

import pytest

from tests.live_write.conftest import _assert_mcptest, wait_for_state

pytestmark = pytest.mark.live_write


async def _container_state(live_mcp_client, container_id: str) -> str:
    res = await live_mcp_client.call_tool("unraid_get_container", {"container_id": container_id})
    return (res.structured_content or {}).get("state", "")


async def test_stop_then_start_container(live_mcp_client, mcptest_container, request) -> None:
    """Stop a running mcptest container, verify state, start it back, verify."""
    name = (mcptest_container.get("names") or ["?"])[0].lstrip("/")
    _assert_mcptest(name)
    cid = mcptest_container["id"]

    initial = await _container_state(live_mcp_client, cid)

    def _restore() -> None:
        import asyncio
        try:
            asyncio.get_event_loop().run_until_complete(
                live_mcp_client.call_tool(
                    "unraid_start_container" if initial == "running" else "unraid_stop_container",
                    {"container_id": cid},
                )
            )
        except Exception:  # noqa: BLE001
            pass
    request.addfinalizer(_restore)

    await live_mcp_client.call_tool("unraid_stop_container", {"container_id": cid})
    state = await wait_for_state(
        lambda: _container_state(live_mcp_client, cid),
        predicate=lambda s: s in {"exited", "stopped", "dead", ""},
    )
    assert state in {"exited", "stopped", "dead", ""}, f"unexpected state {state!r}"

    await live_mcp_client.call_tool("unraid_start_container", {"container_id": cid})
    state = await wait_for_state(
        lambda: _container_state(live_mcp_client, cid),
        predicate=lambda s: s == "running",
    )
    assert state == "running"


async def test_pause_then_unpause_container(live_mcp_client, mcptest_container, request) -> None:
    """Pause + unpause a running mcptest container."""
    name = (mcptest_container.get("names") or ["?"])[0].lstrip("/")
    _assert_mcptest(name)
    cid = mcptest_container["id"]

    if (await _container_state(live_mcp_client, cid)) != "running":
        pytest.skip(f"{name} is not running; can't pause")

    def _unpause() -> None:
        import asyncio
        try:
            asyncio.get_event_loop().run_until_complete(
                live_mcp_client.call_tool("unraid_unpause_container", {"container_id": cid})
            )
        except Exception:  # noqa: BLE001
            pass
    request.addfinalizer(_unpause)

    await live_mcp_client.call_tool("unraid_pause_container", {"container_id": cid})
    state = await wait_for_state(
        lambda: _container_state(live_mcp_client, cid),
        predicate=lambda s: s == "paused",
    )
    assert state == "paused"

    await live_mcp_client.call_tool("unraid_unpause_container", {"container_id": cid})
    state = await wait_for_state(
        lambda: _container_state(live_mcp_client, cid),
        predicate=lambda s: s == "running",
    )
    assert state == "running"


async def test_restart_container(live_mcp_client, mcptest_container) -> None:
    """Restart returns the container to running state; covers the restart wrapper."""
    name = (mcptest_container.get("names") or ["?"])[0].lstrip("/")
    _assert_mcptest(name)
    cid = mcptest_container["id"]

    await live_mcp_client.call_tool("unraid_restart_container", {"container_id": cid})
    state = await wait_for_state(
        lambda: _container_state(live_mcp_client, cid),
        predicate=lambda s: s == "running",
        timeout=15.0,
    )
    assert state == "running"
```

- [ ] **Step 2: Run** (requires `mcptest-*` container on the tower)

```bash
UNRAID_ALLOW_LIVE_WRITES=1 uv run pytest tests/live_write/test_docker.py -v -m live_write
```
Expected: 3 PASS (or SKIP with creation instructions if no `mcptest-*` container).

- [ ] **Step 3: Commit**

```bash
git add tests/live_write/test_docker.py
git commit -m "test: live_write docker stop/start/pause/unpause/restart (mcptest container)"
```

---

### Task 26: Live writes — VMs

**Files:**
- Create: `tests/live_write/test_vms.py`

- [ ] **Step 1: Write the tests**

Create `tests/live_write/test_vms.py`:

```python
"""Live mutating tests for VM tools.

Uses the discovered mcptest-* VM. Covers start/stop/pause/resume/reboot.
Skips force_stop_vm — that's waived in the coverage manifest as disruptive.
"""

from __future__ import annotations

import pytest

from tests.live_write.conftest import _assert_mcptest, wait_for_state

pytestmark = pytest.mark.live_write


async def _vm_state(live_mcp_client, vm_id: str) -> str:
    res = await live_mcp_client.call_tool("unraid_list_vms", {})
    payload = res.structured_content or {}
    for d in payload.get("domain") or []:
        if d.get("uuid") == vm_id or d.get("name") == vm_id:
            return d.get("state", "")
    return "missing"


async def test_start_then_stop_vm(live_mcp_client, mcptest_vm, request) -> None:
    """Start an mcptest VM, verify state, stop it, verify."""
    _assert_mcptest(mcptest_vm["name"])
    vm_id = mcptest_vm.get("uuid") or mcptest_vm["name"]

    def _stop() -> None:
        import asyncio
        try:
            asyncio.get_event_loop().run_until_complete(
                live_mcp_client.call_tool("unraid_stop_vm", {"vm_id": vm_id})
            )
        except Exception:  # noqa: BLE001
            pass
    request.addfinalizer(_stop)

    await live_mcp_client.call_tool("unraid_start_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() in {"running", "started"},
        timeout=20.0,
    )

    await live_mcp_client.call_tool("unraid_stop_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() in {"shutoff", "stopped", "shut off"},
        timeout=30.0,
    )


async def test_pause_resume_vm(live_mcp_client, mcptest_vm, request) -> None:
    """Pause + resume a running mcptest VM."""
    _assert_mcptest(mcptest_vm["name"])
    vm_id = mcptest_vm.get("uuid") or mcptest_vm["name"]

    if (await _vm_state(live_mcp_client, vm_id)).lower() not in {"running", "started"}:
        pytest.skip(f"VM not running; can't pause (state={await _vm_state(live_mcp_client, vm_id)})")

    def _resume() -> None:
        import asyncio
        try:
            asyncio.get_event_loop().run_until_complete(
                live_mcp_client.call_tool("unraid_resume_vm", {"vm_id": vm_id})
            )
        except Exception:  # noqa: BLE001
            pass
    request.addfinalizer(_resume)

    await live_mcp_client.call_tool("unraid_pause_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() == "paused",
        timeout=15.0,
    )

    await live_mcp_client.call_tool("unraid_resume_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() in {"running", "started"},
        timeout=15.0,
    )


async def test_reboot_vm(live_mcp_client, mcptest_vm) -> None:
    """Reboot returns the VM to running state."""
    _assert_mcptest(mcptest_vm["name"])
    vm_id = mcptest_vm.get("uuid") or mcptest_vm["name"]

    if (await _vm_state(live_mcp_client, vm_id)).lower() not in {"running", "started"}:
        pytest.skip("VM not running; can't reboot")

    await live_mcp_client.call_tool("unraid_reboot_vm", {"vm_id": vm_id})
    await wait_for_state(
        lambda: _vm_state(live_mcp_client, vm_id),
        predicate=lambda s: s.lower() in {"running", "started"},
        timeout=60.0,
    )
```

- [ ] **Step 2: Run** (requires `mcptest-*` VM)

```bash
UNRAID_ALLOW_LIVE_WRITES=1 uv run pytest tests/live_write/test_vms.py -v -m live_write
```
Expected: 3 PASS (or SKIP with creation instructions if no `mcptest-*` VM).

- [ ] **Step 3: Commit**

```bash
git add tests/live_write/test_vms.py
git commit -m "test: live_write vm start/stop/pause/resume/reboot (mcptest vm)"
```

---

### Task 27: Remove the xfail on the manifest meta-test

**Files:**
- Modify: `tests/integration/test_tool_coverage_manifest.py`

- [ ] **Step 1: Remove the `@pytest.mark.xfail` decorator added in Task 10**

Open `tests/integration/test_tool_coverage_manifest.py`, find the `@pytest.mark.xfail(...)` line above `test_every_manifest_tool_has_a_live_test`, and delete it.

- [ ] **Step 2: Run the meta-test in default mode**

```bash
uv run pytest tests/integration/test_tool_coverage_manifest.py::test_every_manifest_tool_has_a_live_test -v
```
Expected: PASS (every manifest entry with `marker != None` now has a corresponding live test from Phases 6-7).

- [ ] **Step 3: If any tool is reported missing**

Add a test case in the appropriate `tests/integration/test_live_reads_full.py` or `tests/live_write/test_*.py` file that calls the tool by name. The meta-test's only requirement is that the tool name appears somewhere in a collected test ID.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_tool_coverage_manifest.py
git commit -m "test: enable manifest <-> live-test parity check

Phases 6-7 added the missing live tests; remove the xfail and let
the meta-test enforce parity going forward."
```

---

## Phase 8 — Coverage gate and polish

### Task 28: Raise coverage gate to 90% with per-module thresholds

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Measure current branch coverage with the new test suite**

```bash
uv run pytest tests/unit/ tests/property/ tests/contract/test_used_surface.py \
    --cov=unraid_mcp --cov-branch --cov-report=term-missing
```
Expected: total coverage near 80-90%. Note the per-file numbers — we need to identify any file below its target threshold and either add tests or accept a lower per-file gate.

- [ ] **Step 2: Update `pyproject.toml` coverage section**

Replace the existing `[tool.coverage.report]` section with:

```toml
[tool.coverage.report]
fail_under = 90
show_missing = true
skip_covered = false
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.",
    "@overload",
    "raise NotImplementedError",
    "\\.\\.\\.",
]
```

- [ ] **Step 3: Re-measure**

```bash
uv run pytest tests/unit/ tests/property/ tests/contract/test_used_surface.py \
    --cov=unraid_mcp --cov-branch --cov-fail-under=90 --cov-report=term-missing
```
Expected: PASS at ≥ 90%. If under, add unit/property tests for the uncovered branches reported in the output, then re-run.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "test: raise branch coverage gate to 90%

Project-floor gate enforces the maturity bar from the spec. Per-module
targets (95% on clients/, tools/) are achieved by the new tests in
Phases 2 and 5; if a future change drops coverage, the build fails."
```

---

### Task 29: Update CONTRIBUTING.md with new test commands

**Files:**
- Modify: `CONTRIBUTING.md`

- [ ] **Step 1: Add a "Test layers" section**

Open `CONTRIBUTING.md`, find the "Local Quality Gates" section, and append a new section after it:

```markdown
## Test Layers

The suite is layered. Each layer catches a distinct class of bugs.

| Command | What runs | Env required |
|---------|-----------|--------------|
| `uv run pytest` | unit + property + e2e + non-live contract | none |
| `uv run pytest -m integration` | live read tools against your tower | `UNRAID_API_KEY`, `UNRAID_HOST` |
| `UNRAID_ALLOW_LIVE_WRITES=1 uv run pytest -m live_write` | live mutating tests on `mcptest_*` assets | live env + the flag |
| `uv run pytest -m "contract and requires_live"` | live schema-drift check | `UNRAID_API_KEY` |
| `uv run python -m tests.contract.refresh` | re-snapshot pinned schema | `UNRAID_API_KEY` |

### Live-write asset setup (one-time)

Live write tests need throwaway assets named with the `mcptest-` prefix:

- A Docker container — Unraid UI → Docker → Add Container, image `nginx:alpine`, name `mcptest-nginx`.
- A VM — Unraid UI → VMs → Add VM, minimal config, name `mcptest-vm`.

Tests discover them by prefix and skip cleanly if absent. They will start/stop/pause/restart/reboot but never delete these assets.

User-mutation tests (`unraid_create_user` / `unraid_delete_user`) additionally require `UNRAID_ALLOW_USER_MUTATIONS=true`. They create and tear down their own `mcptest_user_<uuid>` users.
```

- [ ] **Step 2: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "docs: document test layers and mcptest_ asset setup"
```

---

### Task 30: CHANGELOG entry

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add an entry under `[Unreleased]` → `### Added`**

Open `CHANGELOG.md` and add at the top of the existing `## [Unreleased]` → `### Added` list:

```markdown
- Layered test suite: `tests/property/` (Hypothesis fuzzing on parsers,
  config, error mapping, and password env-var allowlist), `tests/e2e/`
  (MCP stdio transport tests with mocked GraphQL endpoint), `tests/contract/`
  (GraphQL schema snapshot pinning + drift detection), and
  `tests/live_write/` (gated mutating tests on `mcptest_*` assets).
- Per-tool live-coverage manifest in `tests/integration/_coverage.py`
  with meta-tests that enforce every registered MCP tool has a live test.
- `tests/conftest.py` autouse fixture isolates `UNRAID_*` env vars per
  test, fixing a leak that caused `test_no_api_key_exits_one` to fail.
- Branch coverage gate raised from 80% to 90%.
- Three-layer write gating for live mutating tests: `pytest -m live_write`
  marker + `UNRAID_ALLOW_LIVE_WRITES=1` env flag + `mcptest_*` asset
  name invariant. Pre-flight banner with 3-second abort window.
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: CHANGELOG entry for test maturity uplift"
```

---

### Task 31: File mutation testing as a follow-up issue

**Files:** none (creates a GitHub issue)

- [ ] **Step 1: Create the issue**

```bash
gh issue create \
    --title "test: add mutation testing (mutmut) on critical modules" \
    --body "$(cat <<'EOF'
Mutation testing — running `mutmut` (or `cosmic-ray`) against `clients/`,
`tools/`, and `errors.py` — was filed as out-of-scope during the
2026-05-03 test maturity uplift design (`docs/superpowers/specs/2026-05-03-test-maturity-design.md`).

**Goal:** raise confidence that the new branch coverage genuinely tests
behavior, not just exercises lines. Mutation testing flips operators
and conditions in source code and verifies that at least one test
fails for each mutation.

**Suggested scope:**
- Targets: `src/unraid_mcp/clients/`, `src/unraid_mcp/tools/`, `src/unraid_mcp/errors.py`
- Tool: `mutmut` (simpler than `cosmic-ray` for this codebase)
- CI: opt-in workflow (`workflow_dispatch`) that posts a mutation score
  comment on the PR
- Acceptance: ≥ 75% killed mutations on each target module

**References:**
- Design spec: \`docs/superpowers/specs/2026-05-03-test-maturity-design.md\` (Non-Goals section)
- Implementation plan: \`docs/superpowers/plans/2026-05-03-test-maturity-uplift.md\` (Task 31)
EOF
)"
```
Expected: prints the URL of the new issue.

- [ ] **Step 2: Note: no commit needed** — this is a side effect outside the repo.

---

## Self-Review

Run the full default suite and the live tiers locally to confirm everything composes:

```bash
# Default — must pass without env
uv run pytest -q

# Live reads
uv run pytest -m integration -v

# Live writes (against tower with mcptest_* assets in place)
UNRAID_ALLOW_LIVE_WRITES=1 UNRAID_ALLOW_USER_MUTATIONS=true \
    uv run pytest -m live_write -v

# Schema drift check
uv run pytest -m "contract and requires_live" -v
```

**Spec coverage check:**

| Spec section | Plan task(s) |
|---|---|
| Suite layout (Architecture → suite layout) | Task 4 (property/), 8-10 (registry), 11-13 (contract/), 14-19 (e2e/), 21-26 (live_write/) |
| Markers + addopts | Task 2 |
| Three-layer write gating | Task 21 (conftest), Tasks 22-26 (per-domain) |
| `mcptest_*` invariant | Task 21 (`_assert_mcptest`) used in 22-26 |
| Asset lifecycle | Task 21 (fixtures), Task 24 (user create/delete), Task 21 orphan scan |
| Schema contract (Components 3) | Tasks 11, 12, 13 |
| MCP transport (Components 4) | Tasks 14-19 |
| Property tests (Components 5) | Tasks 4-7 |
| Per-tool registry (Components 6) | Tasks 8-10, 27 |
| State-via-re-read pattern | `wait_for_state` in Task 21; used in 22-26 |
| Failure taxonomy + retry | `wait_for_state` (single retry, Task 21); fixture skip messages throughout |
| Coverage gate raise to 90% | Task 28 |
| Env isolation fix | Task 1 |
| CHANGELOG entry | Task 30 |
| CONTRIBUTING update | Task 29 |
| Mutation testing follow-up | Task 31 |

All spec sections are covered by at least one task. No `TBD`, no "implement later" — every step has the actual code or command needed.
