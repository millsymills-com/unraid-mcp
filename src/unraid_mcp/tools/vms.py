"""Virtual machine tools (1 read + 6 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unraid_mcp.errors import handle_client_error
from unraid_mcp.models.vms import Vms
from unraid_mcp.tools._helpers import require_client, require_readwrite


def register_vm_tools(mcp: FastMCP) -> None:
    """Register VM tools."""

    @mcp.tool(tags={"vms"})
    async def unraid_list_vms(ctx: Context) -> Vms:
        """List all libvirt VMs (UUID, name, state).

        Args:
            ctx: FastMCP request context.

        Returns:
            ``Vms`` model wrapping the list of ``VmDomain`` entries.
        """
        try:
            client = require_client(ctx)
            return await client.list_vms()
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "vms"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unraid_start_vm(ctx: Context, vm_id: str) -> dict[str, Any]:
        """Start a VM by UUID.

        Args:
            ctx: FastMCP request context.
            vm_id: VM UUID.

        Returns:
            Raw GraphQL mutation response payload.
        """
        try:
            client = require_readwrite(ctx, "start VM")
            return await client.start_vm(vm_id)
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "vms"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    async def unraid_stop_vm(ctx: Context, vm_id: str) -> dict[str, Any]:
        """Gracefully stop a VM by UUID (sends ACPI shutdown).

        Args:
            ctx: FastMCP request context.
            vm_id: VM UUID.

        Returns:
            Raw GraphQL mutation response payload.
        """
        try:
            client = require_readwrite(ctx, "stop VM")
            return await client.stop_vm(vm_id)
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "vms"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    async def unraid_force_stop_vm(ctx: Context, vm_id: str) -> dict[str, Any]:
        """Force-stop a VM by UUID (equivalent to pulling the plug).

        Args:
            ctx: FastMCP request context.
            vm_id: VM UUID.

        Returns:
            Raw GraphQL mutation response payload.
        """
        try:
            client = require_readwrite(ctx, "force-stop VM")
            return await client.force_stop_vm(vm_id)
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "vms"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unraid_pause_vm(ctx: Context, vm_id: str) -> dict[str, Any]:
        """Pause a running VM by UUID.

        Args:
            ctx: FastMCP request context.
            vm_id: VM UUID.

        Returns:
            Raw GraphQL mutation response payload.
        """
        try:
            client = require_readwrite(ctx, "pause VM")
            return await client.pause_vm(vm_id)
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "vms"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unraid_resume_vm(ctx: Context, vm_id: str) -> dict[str, Any]:
        """Resume a paused VM by UUID.

        Args:
            ctx: FastMCP request context.
            vm_id: VM UUID.

        Returns:
            Raw GraphQL mutation response payload.
        """
        try:
            client = require_readwrite(ctx, "resume VM")
            return await client.resume_vm(vm_id)
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "vms"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unraid_reboot_vm(ctx: Context, vm_id: str) -> dict[str, Any]:
        """Reboot a VM by UUID.

        Args:
            ctx: FastMCP request context.
            vm_id: VM UUID.

        Returns:
            Raw GraphQL mutation response payload.
        """
        try:
            client = require_readwrite(ctx, "reboot VM")
            return await client.reboot_vm(vm_id)
        except Exception as e:
            handle_client_error(e)
