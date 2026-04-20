"""User models."""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class UserAccount(UnraidBaseModel):
    """The authenticated Unraid user account (``Query.me``).

    The Unraid API 4.32+ schema dropped ``Query.users`` / ``Mutation.addUser``
    / ``Mutation.deleteUser``; only self-introspection remains. ``roles`` is
    a list in the live schema (e.g. ``["ADMIN", "CONNECT", "GUEST"]``).
    """

    id: str | None = None
    name: str | None = None
    description: str | None = None
    roles: list[str] | None = None
