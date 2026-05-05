"""Property-based tests for UnraidConfig env parsing.

Invariants covered:
- Parsing arbitrary text for UNRAID_HOST never crashes; either yields a
  valid config or raises pydantic.ValidationError naming the offending field.
- `is_readwrite` is true iff UNRAID_MODE casefolds to "readwrite".
- Non-readwrite mode strings either default cleanly or raise — never
  silently flip into readwrite.
- `graphql_url` is `<scheme>://<host>:<port>/graphql` for any well-formed triple.
- `api_enabled` is true iff UNRAID_API_KEY is set and non-empty.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from unraid_mcp.config import UnraidConfig, UnraidMode

pytestmark = pytest.mark.property

# Hypothesis re-runs the test body per generated example but does NOT re-run
# function-scoped fixtures (including the autouse env-isolation fixture from
# tests/conftest.py). That's fine here: each test only writes the env vars it
# cares about on top of a cleaned baseline, and the writes are themselves
# monkeypatched (so they unwind once the test finishes).
_HYPOTHESIS_FIXTURE_OK = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])

# `os.environ` rejects embedded NUL bytes at the OS layer before pydantic ever
# sees the value, so filter them out of any strategy that gets exported via
# monkeypatch.setenv. We're testing the config layer, not the env-var channel.
_no_nul = st.text(min_size=1, max_size=100).filter(lambda s: "\x00" not in s)


@_HYPOTHESIS_FIXTURE_OK
@given(host=_no_nul)
def test_arbitrary_host_never_crashes(monkeypatch: pytest.MonkeyPatch, host: str) -> None:
    """Any string for UNRAID_HOST either parses or raises ValidationError."""
    monkeypatch.setenv("UNRAID_HOST", host)
    try:
        cfg = UnraidConfig()
    except ValidationError as exc:
        # Both outcomes are valid for a property test; pytest.raises doesn't fit.
        assert any("unraid_host" in str(err.get("loc", "")) for err in exc.errors())  # noqa: PT017
        return
    assert cfg.unraid_host == host


@_HYPOTHESIS_FIXTURE_OK
@given(mode=st.sampled_from(["readwrite", "READWRITE", "ReadWrite", "rEaDwRiTe"]))
def test_is_readwrite_case_insensitive(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """`is_readwrite` is true for any casing of `readwrite`."""
    monkeypatch.setenv("UNRAID_MODE", mode.lower())
    cfg = UnraidConfig()
    assert cfg.unraid_mode == UnraidMode.READWRITE
    assert cfg.is_readwrite is True


@_HYPOTHESIS_FIXTURE_OK
@given(mode=st.text(min_size=1, max_size=20).filter(lambda s: s.lower() != "readwrite" and "\x00" not in s))
def test_non_readwrite_modes_either_default_or_raise(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """Anything that isn't `readwrite` either defaults to readonly (if `readonly`)
    or raises ValidationError. Never silently flips into readwrite."""
    monkeypatch.setenv("UNRAID_MODE", mode)
    try:
        cfg = UnraidConfig()
    except ValidationError:
        return
    assert cfg.is_readwrite is False


@_HYPOTHESIS_FIXTURE_OK
@given(
    host=st.text(min_size=1, max_size=50, alphabet=st.characters(min_codepoint=33, max_codepoint=126)),
    port=st.integers(min_value=1, max_value=65535),
    use_https=st.booleans(),
)
def test_graphql_url_well_formed(monkeypatch: pytest.MonkeyPatch, host: str, port: int, use_https: bool) -> None:
    """`graphql_url` is always `<scheme>://<host>:<port>/graphql`."""
    monkeypatch.setenv("UNRAID_HOST", host)
    monkeypatch.setenv("UNRAID_PORT", str(port))
    monkeypatch.setenv("UNRAID_USE_HTTPS", "true" if use_https else "false")
    try:
        cfg = UnraidConfig()
    except ValidationError:
        return
    expected_scheme = "https" if use_https else "http"
    assert cfg.graphql_url == f"{expected_scheme}://{host}:{port}/graphql"
    assert cfg.base_url == f"{expected_scheme}://{host}:{port}"


@_HYPOTHESIS_FIXTURE_OK
@given(api_key=st.one_of(st.none(), st.text(max_size=100).filter(lambda s: "\x00" not in s)))
def test_api_enabled_iff_nonempty_key(monkeypatch: pytest.MonkeyPatch, api_key: str | None) -> None:
    """`api_enabled` is true iff UNRAID_API_KEY is set and non-empty."""
    if api_key is None:
        monkeypatch.delenv("UNRAID_API_KEY", raising=False)
    else:
        monkeypatch.setenv("UNRAID_API_KEY", api_key)
    cfg = UnraidConfig()
    assert cfg.api_enabled == bool(api_key)
