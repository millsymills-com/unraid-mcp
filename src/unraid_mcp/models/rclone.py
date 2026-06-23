"""Rclone backup configuration models.

Mirrors the read half of ``Query.rclone`` (``RCloneBackupSettings``). The
``RCloneRemote.parameters``/``config`` JSON blobs may carry cloud credentials
and are deliberately never modeled or selected (PROTO-012). ``configForm`` (a
UI form schema) is likewise omitted.
"""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class RCloneRemote(UnraidBaseModel):
    """A configured rclone remote (credential fields redacted)."""

    name: str | None = None
    type: str | None = None


class RCloneDrive(UnraidBaseModel):
    """An available rclone provider/driver."""

    name: str | None = None


class RCloneConfig(UnraidBaseModel):
    """Rclone backup configuration (secret-free projection)."""

    remotes: list[RCloneRemote] | None = None
    drives: list[RCloneDrive] | None = None
