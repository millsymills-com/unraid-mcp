"""Plugin inventory and install-operation models.

Mirrors ``Query.plugins`` / ``pluginInstallOperations`` /
``pluginInstallOperation``.
"""

from __future__ import annotations

from typing import Literal

from unraid_mcp.models.common import UnraidBaseModel

PluginInstallStatus = Literal["FAILED", "QUEUED", "RUNNING", "SUCCEEDED"]
"""``PluginInstallStatus`` enum."""


class Plugin(UnraidBaseModel):
    """An installed plugin package with metadata."""

    name: str | None = None
    version: str | None = None
    has_api_module: bool | None = None
    has_cli_module: bool | None = None


class PluginInstallOperation(UnraidBaseModel):
    """A tracked plugin-install operation and its status."""

    id: str | None = None
    url: str | None = None
    name: str | None = None
    status: PluginInstallStatus | str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None
    output: list[str] | None = None
