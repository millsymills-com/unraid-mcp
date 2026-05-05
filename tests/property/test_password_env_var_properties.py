"""Property tests for password_env_var allowlist enforcement.

Critical security invariant: only env var names matching the
`UNRAID_NEW_USER_*` prefix are readable via the password_env_var path.
This prevents an MCP client from fishing for unrelated secrets like
AWS_SECRET_ACCESS_KEY.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from unraid_mcp.errors import UnraidError
from unraid_mcp.tools.users import _PASSWORD_ENV_VAR_PREFIX, _resolve_password

pytestmark = pytest.mark.property

_NO_FUNC_FIXTURE_HEALTHCHECK = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])


@_NO_FUNC_FIXTURE_HEALTHCHECK
@given(
    name=st.text(min_size=1, max_size=50)
    .filter(lambda s: not s.startswith(_PASSWORD_ENV_VAR_PREFIX))
    .filter(lambda s: "\x00" not in s)
    .filter(lambda s: "=" not in s),
)
def test_env_var_outside_prefix_always_rejected(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Any env var name not starting with `UNRAID_NEW_USER_` is rejected,
    even when the var is set to a value."""
    monkeypatch.setenv(name, "actualpassword")
    with pytest.raises(UnraidError) as exc_info:
        _resolve_password(password=None, password_env_var=name)
    assert _PASSWORD_ENV_VAR_PREFIX in str(exc_info.value)


@_NO_FUNC_FIXTURE_HEALTHCHECK
@given(
    suffix=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    )
)
def test_env_var_with_correct_prefix_resolves_when_set(monkeypatch: pytest.MonkeyPatch, suffix: str) -> None:
    """A correctly-prefixed env var that's set returns the env value."""
    name = f"{_PASSWORD_ENV_VAR_PREFIX}{suffix}"
    monkeypatch.setenv(name, "secret123")
    assert _resolve_password(password=None, password_env_var=name) == "secret123"


@_NO_FUNC_FIXTURE_HEALTHCHECK
@given(name=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu",))))
def test_unset_prefixed_env_var_raises_with_name(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """An unset (or empty) prefixed env var produces a clear error naming the var."""
    full = f"{_PASSWORD_ENV_VAR_PREFIX}{name}"
    monkeypatch.delenv(full, raising=False)
    with pytest.raises(UnraidError) as exc_info:
        _resolve_password(password=None, password_env_var=full)
    assert full in str(exc_info.value)


@given(password=st.text(min_size=1, max_size=50).filter(lambda s: "\x00" not in s))
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
