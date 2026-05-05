"""Property tests for handle_client_error invariants.

Asserts every UnraidError subclass maps to ToolError with chained cause,
auth errors mention Authentication + API key, not-found errors say
'not found', NotConfigured mentions UNRAID_API_KEY, arbitrary exceptions
become 'Unexpected error', and incoming ToolErrors pass through verbatim.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError
from hypothesis import HealthCheck, given, settings
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
    UnraidError,
]

_NO_FUNC_FIXTURE_HEALTHCHECK = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])


@_NO_FUNC_FIXTURE_HEALTHCHECK
@given(
    error_cls=st.sampled_from(_UNRAID_ERROR_TYPES),
    msg=st.text(min_size=1, max_size=200).filter(lambda s: "\x00" not in s),
)
def test_every_unraid_error_becomes_tool_error(error_cls: type[UnraidError], msg: str) -> None:
    """Every UnraidError subclass is mapped to ToolError; original is chained."""
    with pytest.raises(ToolError) as exc_info:
        handle_client_error(error_cls(msg))
    assert exc_info.value.__cause__ is not None
    assert isinstance(exc_info.value.__cause__, error_cls)


@_NO_FUNC_FIXTURE_HEALTHCHECK
@given(msg=st.text(min_size=1, max_size=200).filter(lambda s: "\x00" not in s))
def test_auth_error_message_mentions_authentication(msg: str) -> None:
    """Auth errors always produce a ToolError that names Authentication and
    suggests checking the API key — agents need that hint."""
    with pytest.raises(ToolError) as exc_info:
        handle_client_error(UnraidAuthError(msg))
    assert "Authentication" in str(exc_info.value)
    assert "API key" in str(exc_info.value)


@_NO_FUNC_FIXTURE_HEALTHCHECK
@given(msg=st.text(min_size=1, max_size=200).filter(lambda s: "\x00" not in s))
def test_not_found_error_message_mentions_not_found(msg: str) -> None:
    """Not-found errors always say 'not found' so agents can branch on it."""
    with pytest.raises(ToolError) as exc_info:
        handle_client_error(UnraidNotFoundError(msg))
    assert "not found" in str(exc_info.value).lower()


@_NO_FUNC_FIXTURE_HEALTHCHECK
@given(msg=st.text(min_size=1, max_size=200).filter(lambda s: "\x00" not in s))
def test_unconfigured_message_names_env_var(msg: str) -> None:
    """`not configured` errors mention UNRAID_API_KEY so the user knows what to set."""
    with pytest.raises(ToolError) as exc_info:
        handle_client_error(UnraidNotConfiguredError(msg))
    assert "UNRAID_API_KEY" in str(exc_info.value)


@_NO_FUNC_FIXTURE_HEALTHCHECK
@given(msg=st.text(min_size=1, max_size=200).filter(lambda s: "\x00" not in s))
def test_arbitrary_exception_becomes_unexpected_tool_error(msg: str) -> None:
    """A non-Unraid exception is wrapped as 'Unexpected error' ToolError."""
    with pytest.raises(ToolError) as exc_info:
        handle_client_error(RuntimeError(msg))
    assert "Unexpected error" in str(exc_info.value)


def test_tool_error_passes_through_unwrapped() -> None:
    """An incoming ToolError must be re-raised verbatim, not wrapped again
    under 'Unexpected error' — preserves the original message for agents."""
    original = ToolError("original message")
    with pytest.raises(ToolError) as exc_info:
        handle_client_error(original)
    assert exc_info.value is original
