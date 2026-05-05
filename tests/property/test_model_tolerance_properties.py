"""Property tests for Pydantic model tolerance to unknown / arbitrary fields.

UnraidBaseModel sets extra="allow" + alias_generator=to_camel +
populate_by_name=True. Invariants verified here:

- Adding arbitrary unknown JSON-shaped fields to any payload never raises.
- A round-trip of any known field (set by snake_case name) survives
  model_validate -> model_dump and is observable on the instance.
- Both snake_case and the to_camel alias accept the same value.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic.alias_generators import to_camel

from unraid_mcp.models.docker import DockerContainer
from unraid_mcp.models.notifications import Notification
from unraid_mcp.models.shares import Share
from unraid_mcp.models.users import User

pytestmark = pytest.mark.property

_NO_FUNC_FIXTURE_HEALTHCHECK = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])

_MODEL_FIELDS: list[tuple[type, str, object]] = [
    (DockerContainer, "id", "abc123"),
    (DockerContainer, "image", "nginx:alpine"),
    (DockerContainer, "auto_start", True),
    (Notification, "id", "n1"),
    (Notification, "title", "test title"),
    (Notification, "importance", "INFO"),
    (Share, "name", "data"),
    (Share, "size", "10G"),
    (Share, "split_level", "2"),
    (User, "name", "root"),
    (User, "description", "admin user"),
    (User, "roles", "admin"),
]


_JSON_VALUES = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**9), max_value=10**9),
    st.text(max_size=50).filter(lambda s: "\x00" not in s),
)


@pytest.mark.parametrize(("model_cls", "field", "value"), _MODEL_FIELDS)
@_NO_FUNC_FIXTURE_HEALTHCHECK
@given(
    extras=st.dictionaries(
        st.text(min_size=1, max_size=20).filter(lambda s: not s.startswith("_") and "\x00" not in s),
        _JSON_VALUES,
        max_size=10,
    )
)
def test_unknown_fields_tolerated_and_known_round_trips(
    model_cls: type, field: str, value: object, extras: dict[str, object]
) -> None:
    """Arbitrary extras don't crash validation; the known field survives."""
    extras.pop(field, None)
    extras.pop(to_camel(field), None)

    payload = {**extras, field: value}
    instance = model_cls.model_validate(payload)
    assert getattr(instance, field) == value


@pytest.mark.parametrize(("model_cls", "field", "value"), _MODEL_FIELDS)
def test_camel_case_alias_accepted(model_cls: type, field: str, value: object) -> None:
    """The camelCase alias for any snake_case field accepts the same value
    (populate_by_name=True + alias_generator=to_camel)."""
    camel = to_camel(field)
    instance = model_cls.model_validate({camel: value})
    assert getattr(instance, field) == value
