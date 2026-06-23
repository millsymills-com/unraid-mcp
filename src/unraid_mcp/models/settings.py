"""Display / API settings / service models.

Mirrors ``Query.display``, ``Query.settings`` (``.api`` branch only), and
``Query.services``.
"""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class DisplayCase(UnraidBaseModel):
    """Server case display configuration.

    ``base64`` (a large encoded case image) is intentionally not modeled or
    selected — it carries no agent value (plan §3 default-omit).
    """

    url: str | None = None
    icon: str | None = None
    error: str | None = None


class DisplaySettings(UnraidBaseModel):
    """UI display settings."""

    id: str | None = None
    case: DisplayCase | None = None
    theme: str | None = None
    unit: str | None = None
    scale: bool | None = None
    tabs: bool | None = None
    resize: bool | None = None
    wwn: bool | None = None
    total: bool | None = None
    usage: bool | None = None
    text: bool | None = None
    warning: int | None = None
    critical: int | None = None
    hot: int | None = None
    max: int | None = None
    locale: str | None = None


class ApiConfig(UnraidBaseModel):
    """The ``settings.api`` configuration branch."""

    version: str | None = None
    extra_origins: list[str] | None = None
    sandbox: bool | None = None
    plugins: list[str] | None = None


class ApiSettings(UnraidBaseModel):
    """Top-level settings envelope, ``.api`` branch only."""

    id: str | None = None
    api: ApiConfig | None = None


class ServiceUptime(UnraidBaseModel):
    """A service's uptime marker."""

    timestamp: str | None = None


class Service(UnraidBaseModel):
    """A background service's status."""

    id: str | None = None
    name: str | None = None
    online: bool | None = None
    uptime: ServiceUptime | None = None
    version: str | None = None
