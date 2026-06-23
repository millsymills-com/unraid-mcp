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
        return None
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

    Optional policy — fields are blanket-``Optional[...] = None`` on purpose,
    even where the schema marks them non-null (``!``). Tools select narrow
    field subsets and the API may return partial objects on degraded or
    permission-limited responses; combined with ``extra="allow"``, this keeps
    deserialization total — a missing field yields ``None`` rather than a
    validation error. ``Literal[...]`` is still applied to genuinely
    enum-backed fields to constrain their values when present.
    """

    model_config = ConfigDict(
        extra="allow",
        alias_generator=to_camel,
        populate_by_name=True,
        # Unraid exposes fields like ``modelName`` (UPS config); without this
        # Pydantic warns on any field colliding with its ``model_`` namespace.
        protected_namespaces=(),
    )
