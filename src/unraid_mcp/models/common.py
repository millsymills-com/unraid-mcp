"""Shared model types for Unraid GraphQL responses."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


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
