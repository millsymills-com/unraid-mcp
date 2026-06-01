"""Offline regression tests for the live-write three-layer safety gate.

The ``tests/live_write/`` suite is protected by three independent layers
(pytest marker + ``UNRAID_ALLOW_LIVE_WRITES=1`` env flag + ``mcptest_*`` name
regex). Layers 2 and 3 are load-bearing single expressions: a refactor that
flips a negation, drops ``.lower()``, or loosens ``startswith`` to a substring
match would silently disarm the guard with zero live-test signal (the live
suite skips entirely in CI). These tests pin the current behavior so such a
regression fails offline.

The guards live in ``tests.live_write._gates`` — a fixture-free module — so
importing them here does not activate the live suite's session-scoped autouse
gate (which would otherwise skip this whole file).
"""

from __future__ import annotations

import pytest

from tests.live_write._gates import assert_mcptest, require_writes_enabled


class TestAssertMcptest:
    """Layer 3: every live-write fixture routes asset names through this guard."""

    def test_rejects_non_mcptest_name(self) -> None:
        with pytest.raises(RuntimeError, match="refusing to mutate"):
            assert_mcptest("production-db")

    def test_accepts_mcptest_prefix(self) -> None:
        assert_mcptest("mcptest-foo")

    def test_accepts_bare_prefix(self) -> None:
        assert_mcptest("mcptest")

    def test_rejects_none(self) -> None:
        with pytest.raises(RuntimeError):
            assert_mcptest(None)

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(RuntimeError):
            assert_mcptest("")

    def test_rejects_leading_space(self) -> None:
        # ``startswith`` anchors at index 0, so a leading space defeats the match.
        with pytest.raises(RuntimeError):
            assert_mcptest(" mcptest-foo")

    def test_rejects_substring_match(self) -> None:
        # The guard must be a prefix check, not a substring check.
        with pytest.raises(RuntimeError):
            assert_mcptest("prod-mcptest-db")

    def test_accepts_uppercase_via_lowercasing(self) -> None:
        # Current behavior lowercases before comparing — pin it explicitly so a
        # future drop of ``.lower()`` is a deliberate, test-breaking change.
        assert_mcptest("MCPTEST_x")


@pytest.fixture
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize the ``.env`` loader and any inherited live-write env vars.

    ``require_writes_enabled`` imports the loader from ``tests.conftest`` at
    call time, so patching the attribute there is enough.
    """
    monkeypatch.setattr("tests.conftest.load_unraid_env_into_os_environ", lambda: None)
    monkeypatch.delenv("UNRAID_ALLOW_LIVE_WRITES", raising=False)
    monkeypatch.delenv("UNRAID_API_KEY", raising=False)


@pytest.mark.usefixtures("_no_dotenv")
class TestRequireWritesEnabled:
    """Layer 2: the directory-wide env-flag gate that must default to skipping."""

    @pytest.mark.parametrize("value", ["0", "true", "yes", "", "TRUE", "1 "])
    def test_skips_unless_flag_is_exactly_1(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("UNRAID_ALLOW_LIVE_WRITES", value)
        monkeypatch.setenv("UNRAID_API_KEY", "dummy")
        with pytest.raises(pytest.skip.Exception, match="gated"):
            require_writes_enabled()

    def test_skips_when_flag_unset(self) -> None:
        with pytest.raises(pytest.skip.Exception, match="gated"):
            require_writes_enabled()

    def test_skips_when_enabled_but_api_key_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UNRAID_ALLOW_LIVE_WRITES", "1")
        with pytest.raises(pytest.skip.Exception, match="UNRAID_API_KEY"):
            require_writes_enabled()

    def test_passes_when_enabled_and_api_key_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UNRAID_ALLOW_LIVE_WRITES", "1")
        monkeypatch.setenv("UNRAID_API_KEY", "dummy")
        require_writes_enabled()
