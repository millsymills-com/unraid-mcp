"""Per-tool live-coverage manifest for integration tests.

Declares every MCP tool registered by ``unraid_mcp`` with its expected live
coverage marker. The ``TOOLS`` list is the single source of truth used by
integration test parametrization and by completeness assertions that detect
when the registered tool surface drifts from this manifest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Marker = Literal["integration", "live_write"]


@dataclass(frozen=True)
class ToolCoverage:
    """Live-coverage declaration for a single MCP tool."""

    name: str
    reads: bool
    writes: bool
    marker: Marker | None
    needs_asset: str | None = None
    extra_gate: str | None = None
    skip_reason: str | None = None

    def __post_init__(self) -> None:
        if self.marker is None and self.skip_reason is None:
            msg = f"{self.name}: skip_reason is required when marker is None"
            raise ValueError(msg)
        if self.writes and self.marker == "integration":
            msg = f"{self.name}: write tools cannot use marker='integration'"
            raise ValueError(msg)


TOOLS: list[ToolCoverage] = [
    # ── system ──
    ToolCoverage(name="unraid_get_info", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_get_flash", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_get_registration", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_get_connect", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_get_network", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_get_cloud", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_list_services", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_get_display_settings", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_get_api_settings", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_get_system_time", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_list_timezone_options", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_get_vars", reads=True, writes=False, marker="integration"),
    # ── metrics ──
    ToolCoverage(name="unraid_get_metrics", reads=True, writes=False, marker="integration"),
    # ── ups ──
    ToolCoverage(name="unraid_list_ups_devices", reads=True, writes=False, marker="integration"),
    ToolCoverage(
        name="unraid_get_ups_device",
        reads=True,
        writes=False,
        marker=None,
        skip_reason="requires a known UPS device id; no stable live asset",
    ),
    ToolCoverage(name="unraid_get_ups_configuration", reads=True, writes=False, marker="integration"),
    # ── plugins ──
    ToolCoverage(name="unraid_list_plugins", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_list_installed_plugins", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_list_plugin_install_operations", reads=True, writes=False, marker="integration"),
    ToolCoverage(
        name="unraid_get_plugin_install_operation",
        reads=True,
        writes=False,
        marker=None,
        skip_reason="requires a known operation id; no stable live asset",
    ),
    # ── logs ──
    ToolCoverage(name="unraid_list_log_files", reads=True, writes=False, marker="integration"),
    ToolCoverage(
        name="unraid_read_log_file",
        reads=True,
        writes=False,
        marker=None,
        skip_reason="requires a known log path; covered indirectly via list_log_files",
    ),
    # ── oidc ──
    ToolCoverage(name="unraid_get_sso_status", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_list_public_oidc_providers", reads=True, writes=False, marker="integration"),
    # ── rclone ──
    ToolCoverage(name="unraid_get_rclone_config", reads=True, writes=False, marker="integration"),
    # ── array ──
    ToolCoverage(name="unraid_get_array", reads=True, writes=False, marker="integration"),
    ToolCoverage(
        name="unraid_start_array",
        reads=False,
        writes=True,
        marker=None,
        skip_reason="disruptive — array start/stop is out of scope per spec",
    ),
    ToolCoverage(
        name="unraid_stop_array",
        reads=False,
        writes=True,
        marker=None,
        skip_reason="disruptive — array start/stop is out of scope per spec",
    ),
    # ── parity ──
    ToolCoverage(name="unraid_get_parity_history", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_start_parity_check", reads=False, writes=True, marker="live_write"),
    ToolCoverage(name="unraid_pause_parity_check", reads=False, writes=True, marker="live_write"),
    ToolCoverage(name="unraid_resume_parity_check", reads=False, writes=True, marker="live_write"),
    ToolCoverage(name="unraid_cancel_parity_check", reads=False, writes=True, marker="live_write"),
    # ── disks ──
    ToolCoverage(name="unraid_list_disks", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_get_disk", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_list_assignable_disks", reads=True, writes=False, marker="integration"),
    # ── docker ──
    ToolCoverage(name="unraid_list_containers", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_get_container", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_list_docker_networks", reads=True, writes=False, marker="integration"),
    ToolCoverage(
        name="unraid_start_container",
        reads=False,
        writes=True,
        marker="live_write",
        needs_asset="mcptest_container",
    ),
    ToolCoverage(
        name="unraid_stop_container",
        reads=False,
        writes=True,
        marker="live_write",
        needs_asset="mcptest_container",
    ),
    ToolCoverage(
        name="unraid_restart_container",
        reads=False,
        writes=True,
        marker="live_write",
        needs_asset="mcptest_container",
    ),
    ToolCoverage(
        name="unraid_pause_container",
        reads=False,
        writes=True,
        marker="live_write",
        needs_asset="mcptest_container",
    ),
    ToolCoverage(
        name="unraid_unpause_container",
        reads=False,
        writes=True,
        marker="live_write",
        needs_asset="mcptest_container",
    ),
    # ── vms ──
    ToolCoverage(name="unraid_list_vms", reads=True, writes=False, marker="integration"),
    ToolCoverage(
        name="unraid_start_vm",
        reads=False,
        writes=True,
        marker="live_write",
        needs_asset="mcptest_vm",
    ),
    ToolCoverage(
        name="unraid_stop_vm",
        reads=False,
        writes=True,
        marker="live_write",
        needs_asset="mcptest_vm",
    ),
    ToolCoverage(
        name="unraid_force_stop_vm",
        reads=False,
        writes=True,
        marker=None,
        needs_asset="mcptest_vm",
        skip_reason="disruptive — force_stop is out of scope per spec",
    ),
    ToolCoverage(
        name="unraid_pause_vm",
        reads=False,
        writes=True,
        marker="live_write",
        needs_asset="mcptest_vm",
    ),
    ToolCoverage(
        name="unraid_resume_vm",
        reads=False,
        writes=True,
        marker="live_write",
        needs_asset="mcptest_vm",
    ),
    ToolCoverage(
        name="unraid_reboot_vm",
        reads=False,
        writes=True,
        marker="live_write",
        needs_asset="mcptest_vm",
    ),
    # ── shares ──
    ToolCoverage(name="unraid_list_shares", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_get_share", reads=True, writes=False, marker="integration"),
    # ── users ──
    ToolCoverage(name="unraid_get_me", reads=True, writes=False, marker="integration"),
    # ── notifications ──
    ToolCoverage(name="unraid_list_notifications", reads=True, writes=False, marker="integration"),
    ToolCoverage(name="unraid_archive_notification", reads=False, writes=True, marker="live_write"),
    ToolCoverage(name="unraid_delete_notification", reads=False, writes=True, marker="live_write"),
    ToolCoverage(name="unraid_archive_all_notifications", reads=False, writes=True, marker="live_write"),
]


_BY_NAME: dict[str, ToolCoverage] = {tool.name: tool for tool in TOOLS}


def by_name(name: str) -> ToolCoverage:
    """Return the ``ToolCoverage`` entry for ``name`` or raise ``KeyError``."""

    return _BY_NAME[name]
