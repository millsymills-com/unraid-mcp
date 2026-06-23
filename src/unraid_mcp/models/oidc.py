"""OIDC / SSO models.

Only the secret-free ``PublicOidcProvider`` projection is modeled. The admin
``OidcProvider`` type (which carries ``clientSecret``) is deliberately never
modeled or selected (PROTO-012).
"""

from __future__ import annotations

from unraid_mcp.models.common import UnraidBaseModel


class PublicOidcProvider(UnraidBaseModel):
    """A public OIDC provider, as surfaced for login buttons (no secrets)."""

    id: str | None = None
    name: str | None = None
    button_text: str | None = None
    button_icon: str | None = None
    button_variant: str | None = None
    button_style: str | None = None
