"""Tool tests for the VMs domain."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from unraid_mcp.models.vms import VmDomain, Vms


class TestListVms:
    async def test_returns_vms_with_domains(self, client_rw):
        client, mock = client_rw
        mock.list_vms.return_value = Vms(domain=[VmDomain(uuid="u1", name="win11", state="RUNNING")])
        result = await client.call_tool("unraid_list_vms")
        assert result.structured_content["domain"][0]["name"] == "win11"


class TestWriteVmOps:
    @pytest.mark.parametrize(
        ("tool_name", "client_method"),
        [
            ("unraid_start_vm", "start_vm"),
            ("unraid_stop_vm", "stop_vm"),
            ("unraid_force_stop_vm", "force_stop_vm"),
            ("unraid_pause_vm", "pause_vm"),
            ("unraid_resume_vm", "resume_vm"),
            ("unraid_reboot_vm", "reboot_vm"),
        ],
    )
    async def test_write_tool_forwards_id_and_returns_ok_shape(self, client_rw, tool_name, client_method):
        # Drift #60: VM mutations return ``Boolean!`` — the client
        # normalises to ``{"ok": bool, "id": vm_id}``.
        client, mock = client_rw
        getattr(mock, client_method).return_value = {"ok": True, "id": "u1"}
        result = await client.call_tool(tool_name, {"vm_id": "u1"})
        getattr(mock, client_method).assert_awaited_once_with("u1")
        assert result.structured_content == {"ok": True, "id": "u1"}

    async def test_force_stop_hidden_in_readonly(self, client_ro):
        client, _ = client_ro
        with pytest.raises(ToolError, match="Unknown tool"):
            await client.call_tool("unraid_force_stop_vm", {"vm_id": "u1"})
