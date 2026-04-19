"""Notification models."""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class Notification(UnraidBaseModel):
    """A notification entry."""

    id: str | None = None
    type: str | None = None
    title: str | None = None
    subject: str | None = None
    description: str | None = None
    importance: str | None = None
    link: str | None = None
    timestamp: str | None = None
    formatted_timestamp: str | None = None
