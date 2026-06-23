"""OIDC / SSO tools (read-only, secret-free)."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from unraid_mcp.models.oidc import PublicOidcProvider
from unraid_mcp.tools._helpers import require_client, unraid_tool


def register_oidc_tools(mcp: FastMCP) -> None:
    """Register OIDC / SSO status tools."""

    @unraid_tool(mcp, tags={"oidc"})
    async def unraid_get_sso_status(ctx: Context) -> bool:
        """Report whether single sign-on (SSO) is enabled on the server.

        Args:
            ctx: FastMCP request context.

        Returns:
            ``True`` if SSO is enabled, ``False`` otherwise.
        """
        client = require_client(ctx)
        return await client.get_sso_status()

    @unraid_tool(mcp, tags={"oidc"})
    async def unraid_list_public_oidc_providers(ctx: Context) -> list[PublicOidcProvider]:
        """List public OIDC providers shown on the login screen.

        Returns only the secret-free login-button projection — provider client
        secrets are never exposed.

        Args:
            ctx: FastMCP request context.

        Returns:
            List of ``PublicOidcProvider`` models.
        """
        client = require_client(ctx)
        return await client.list_public_oidc_providers()
