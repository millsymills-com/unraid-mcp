"""User models."""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class User(UnraidBaseModel):
    """An Unraid user."""

    id: str | None = None
    name: str | None = None
    description: str | None = None
    roles: str | None = None
