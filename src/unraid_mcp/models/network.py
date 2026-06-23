"""Network and cloud models. Mirrors ``Query.network`` / ``Query.cloud``."""

from __future__ import annotations

from typing import Literal

from unraid_mcp.models.common import UnraidBaseModel

AccessUrlType = Literal["LAN", "WIREGUARD", "WAN", "MDNS", "OTHER", "DEFAULT"]
"""``URL_TYPE`` enum."""

MinigraphStatus = Literal["PRE_INIT", "CONNECTING", "CONNECTED", "PING_FAILURE", "ERROR_RETRYING"]
"""``MinigraphStatus`` enum."""


class AccessUrl(UnraidBaseModel):
    """A single network access URL (LAN / WAN / etc.)."""

    type: AccessUrlType | None = None
    name: str | None = None
    ipv4: str | None = None
    ipv6: str | None = None


class Network(UnraidBaseModel):
    """Network access URLs for the server."""

    id: str | None = None
    access_urls: list[AccessUrl] | None = None


class ApiKeyHealth(UnraidBaseModel):
    """API-key validity health (key material itself is never selected)."""

    valid: bool | None = None
    error: str | None = None


class RelayHealth(UnraidBaseModel):
    """Unraid Connect relay health."""

    status: str | None = None
    timeout: str | None = None
    error: str | None = None


class MinigraphHealth(UnraidBaseModel):
    """Mini-GraphQL link health."""

    status: MinigraphStatus | None = None
    timeout: int | None = None
    error: str | None = None


class CloudStatus(UnraidBaseModel):
    """Cloud reachability status."""

    status: str | None = None
    ip: str | None = None
    error: str | None = None


class Cloud(UnraidBaseModel):
    """Unraid Connect cloud health (secret-free)."""

    error: str | None = None
    api_key: ApiKeyHealth | None = None
    relay: RelayHealth | None = None
    minigraphql: MinigraphHealth | None = None
    cloud: CloudStatus | None = None
    allowed_origins: list[str] | None = None
