"""Notification models."""

from __future__ import annotations

from typing import Literal

from unraid_mcp.models.common import UnraidBaseModel

NotificationType = Literal["UNREAD", "ARCHIVE"]
"""Which notification bin to act on (#61)."""

NotificationImportance = Literal["INFO", "WARNING", "ALERT"]
"""Server-side importance filter accepted by ``archiveAll`` (#61)."""


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
