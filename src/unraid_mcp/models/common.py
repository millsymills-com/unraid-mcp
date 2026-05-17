"""Shared model types for Unraid GraphQL responses."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict
from pydantic.alias_generators import to_camel


def _coerce_bigint(value: object) -> object:
    """Coerce GraphQL ``BigInt`` scalars to a canonical string.

    Unraid's ``BigInt`` is serialized as a JSON number on current builds
    and as a JSON string on older ones. Pydantic ``str`` fields reject
    integers, so the live tests caught the mismatch — accept both forms
    here and let the rest of the model declare ``BigInt`` once.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value)
    return value


BigInt = Annotated[str | None, BeforeValidator(_coerce_bigint)]


class UnraidBaseModel(BaseModel):
    """Base model for Unraid API responses.

    - ``extra="allow"`` keeps unknown fields around so API additions don't
      break existing callers.
    - ``alias_generator=to_camel`` plus ``populate_by_name=True`` lets us
      declare Python-idiomatic snake_case fields that map onto the GraphQL
      API's camelCase shape (``num_reads`` ↔ ``numReads``) while still
      accepting either form in tests.
    """

    model_config = ConfigDict(
        extra="allow",
        alias_generator=to_camel,
        populate_by_name=True,
    )
