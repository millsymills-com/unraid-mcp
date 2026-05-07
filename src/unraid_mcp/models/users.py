"""User models."""

from __future__ import annotations

from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

from unraid_mcp.models.common import UnraidBaseModel


class User(UnraidBaseModel):
    """An Unraid user.

    Defense-in-depth (#132): the base ``UnraidBaseModel`` allows unknown
    fields, but ``User`` overrides that to ``extra="ignore"`` so a
    server-pushed credential field (e.g., ``password`` from
    ``/etc/shadow``) cannot reach ``model_dump()`` and leak into MCP
    transcripts even if the GraphQL query is later changed to request
    it or the Unraid server returns it unsolicited.
    """

    model_config = ConfigDict(
        extra="ignore",
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: str | None = None
    name: str | None = None
    description: str | None = None
    roles: str | None = None
