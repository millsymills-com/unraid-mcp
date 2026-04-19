"""Unraid user tools (1 read + 2 write)."""

from __future__ import annotations

import os
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from pydantic import Field

from unraid_mcp.errors import UnraidError, handle_client_error
from unraid_mcp.models.users import User
from unraid_mcp.tools._helpers import require_client, require_user_mutation

# Only env vars starting with this prefix are readable via `password_env_var`
# — prevents an MCP client from fishing for arbitrary secrets like
# `AWS_SECRET_ACCESS_KEY`. Operators supply the password by setting e.g.
# `UNRAID_NEW_USER_ALICE_PASSWORD=...` and passing `password_env_var=
# "UNRAID_NEW_USER_ALICE_PASSWORD"` to the tool call.
_PASSWORD_ENV_VAR_PREFIX = "UNRAID_NEW_USER_"  # noqa: S105  # nosec B105 — allowlist prefix, not a credential


def _resolve_password(password: str | None, password_env_var: str | None) -> str:
    """Return the effective password, validating mutual exclusion and the env var allowlist.

    Raises:
        UnraidError: on any validation failure. The name of the env var
            may appear in error messages, but the resolved value never does.
    """
    if (password is None) == (password_env_var is None):
        raise UnraidError("Provide exactly one of `password` or `password_env_var`.")
    if password is not None:
        return password
    assert password_env_var is not None  # narrowed by the xor check above
    if not password_env_var.startswith(_PASSWORD_ENV_VAR_PREFIX):
        raise UnraidError(
            f"`password_env_var` must start with '{_PASSWORD_ENV_VAR_PREFIX}' "
            "(restricted to avoid exposing unrelated secrets).",
        )
    resolved = os.environ.get(password_env_var)
    if not resolved:
        raise UnraidError(f"Env var '{password_env_var}' is unset or empty.")
    return resolved


def register_user_tools(mcp: FastMCP) -> None:
    """Register user tools."""

    @mcp.tool(tags={"users"})
    async def unraid_list_users(ctx: Context) -> list[User]:
        """List Unraid users (id, name, description, roles)."""
        try:
            client = require_client(ctx)
            return await client.list_users()
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(
        tags={"write", "users", "user-mutation"},
        annotations={"readOnlyHint": False, "destructiveHint": False},
    )
    async def unraid_create_user(
        ctx: Context,
        name: str,
        password: Annotated[
            str | None,
            Field(
                description=(
                    "Initial password — will be transmitted over the GraphQL connection. "
                    "Mutually exclusive with `password_env_var`."
                ),
                json_schema_extra={"format": "password", "writeOnly": True},
            ),
        ] = None,
        password_env_var: Annotated[
            str | None,
            Field(
                description=(
                    "Name of a server-side env var holding the password. Must begin "
                    f"with '{_PASSWORD_ENV_VAR_PREFIX}'. Use this to keep the password "
                    "out of MCP transcripts and client logs. Mutually exclusive with `password`."
                ),
            ),
        ] = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Unraid user.

        Provide the password either inline via ``password`` or indirectly via
        ``password_env_var`` (which reads from a server-side env var whose name
        begins with ``UNRAID_NEW_USER_``). The env-var path keeps the password
        out of MCP transcripts and client logs.

        Only one of ``password`` or ``password_env_var`` may be set per call.

        **Security note**: when ``password`` is used, the value is sent over
        the network in the GraphQL request body and may appear in client logs.
        Prefer ``password_env_var`` in production and rotate via the Unraid
        WebGUI. Keep logging below DEBUG — httpx surfaces request bodies at
        that level.

        Args:
            name: Username (must be unique).
            password: Inline password. Mutually exclusive with ``password_env_var``.
            password_env_var: Name of a server-side env var (must start with
                ``UNRAID_NEW_USER_``). Mutually exclusive with ``password``.
            description: Optional description shown in the WebGUI.
        """
        try:
            client = require_user_mutation(ctx, "create user")
            effective_password = _resolve_password(password, password_env_var)
            return await client.create_user(
                name=name,
                password=effective_password,
                description=description,
            )
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(
        tags={"write", "users", "user-mutation"},
        annotations={"readOnlyHint": False, "destructiveHint": True},
    )
    async def unraid_delete_user(ctx: Context, name: str) -> dict[str, Any]:
        """Delete an Unraid user by name.

        Args:
            name: Username to delete.
        """
        try:
            client = require_user_mutation(ctx, "delete user")
            return await client.delete_user(name)
        except Exception as e:
            handle_client_error(e)
