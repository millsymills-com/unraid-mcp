"""Unraid GraphQL client with typed query and mutation methods."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from unraid_mcp.clients.base import BaseGraphQLClient
from unraid_mcp.errors import UnraidConnectionError
from unraid_mcp.models.array import ArrayState, ParityHistoryEntry
from unraid_mcp.models.disks import Disk
from unraid_mcp.models.docker import DockerContainer, DockerNetwork
from unraid_mcp.models.notifications import Notification
from unraid_mcp.models.shares import Share
from unraid_mcp.models.system import SystemInfo
from unraid_mcp.models.users import UserAccount
from unraid_mcp.models.vms import Vms

logger = logging.getLogger(__name__)

# Validation goes around the retry loop to fail fast on first-run typos.
_VALIDATION_TIMEOUT_SECONDS = 5


# ── Queries ─────────────────────────────────────────────────────────────

QUERY_INFO = """
query Info {
    info {
        os { platform distro release codename kernel arch hostname uptime }
        cpu { manufacturer brand vendor family model stepping speed cores threads processors }
        memory { total free used active available }
        baseboard { manufacturer model version serial }
        versions { unraid kernel openssl docker }
    }
}
"""

QUERY_ARRAY = """
query Array {
    array {
        state
        capacity { kilobytes { free used total } }
        boot { id name device }
        parities { id name device size status temp }
        disks {
            id name device size status temp numReads numWrites numErrors fsSize fsFree fsUsed type
        }
        caches {
            id name device size status temp numReads numWrites numErrors fsSize fsFree fsUsed type
        }
    }
}
"""

QUERY_PARITY_HISTORY = """
query ParityHistory {
    parityHistory { date duration speed status errors }
}
"""

QUERY_DISKS = """
query Disks {
    disks {
        id name device type size temp rotational interface serialNum smartStatus
    }
}
"""

QUERY_DOCKER_CONTAINERS = """
query DockerContainers {
    dockerContainers {
        id names image imageId command created state status ports {
            ip privatePort publicPort type
        }
        autoStart networkMode
    }
}
"""

QUERY_DOCKER_NETWORKS = """
query DockerNetworks {
    dockerNetworks { id name driver scope created internal attachable ingress }
}
"""

QUERY_VMS = """
query Vms {
    vms {
        domain { uuid name state }
    }
}
"""

QUERY_SHARES = """
query Shares {
    shares {
        name comment free size used include exclude cache nameOrig
        allocator floor splitLevel cow color luksStatus
    }
}
"""

# Verified against Unraid API 4.32+ schema — `Query.users` was removed.
# Only self-introspection survives via `Query.me`.
QUERY_ME = """
query Me {
    me { id name description roles }
}
"""

QUERY_NOTIFICATIONS = """
query Notifications {
    notifications {
        id type title subject description importance link timestamp formattedTimestamp
    }
}
"""

QUERY_FLASH = """
query Flash { flash { guid vendor product } }
"""

QUERY_REGISTRATION = """
query Registration { registration { state expiration type updateExpiration } }
"""

QUERY_CONNECT = """
query Connect {
    connect {
        dynamicRemoteAccessType
        config { accessType forwardType port }
    }
}
"""


# ── Mutations ───────────────────────────────────────────────────────────

MUTATION_START_ARRAY = """
mutation StartArray { startArray { state } }
"""

MUTATION_STOP_ARRAY = """
mutation StopArray { stopArray { state } }
"""

MUTATION_START_PARITY_CHECK = """
mutation StartParityCheck($correct: Boolean) {
    startParityCheck(correct: $correct) { state }
}
"""

MUTATION_PAUSE_PARITY_CHECK = """
mutation PauseParityCheck { pauseParityCheck { state } }
"""

MUTATION_RESUME_PARITY_CHECK = """
mutation ResumeParityCheck { resumeParityCheck { state } }
"""

MUTATION_CANCEL_PARITY_CHECK = """
mutation CancelParityCheck { cancelParityCheck { state } }
"""

MUTATION_START_CONTAINER = """
mutation StartContainer($id: ID!) {
    docker { start(id: $id) { id state status } }
}
"""

MUTATION_STOP_CONTAINER = """
mutation StopContainer($id: ID!) {
    docker { stop(id: $id) { id state status } }
}
"""

MUTATION_RESTART_CONTAINER = """
mutation RestartContainer($id: ID!) {
    docker { restart(id: $id) { id state status } }
}
"""

MUTATION_PAUSE_CONTAINER = """
mutation PauseContainer($id: ID!) {
    docker { pause(id: $id) { id state status } }
}
"""

MUTATION_UNPAUSE_CONTAINER = """
mutation UnpauseContainer($id: ID!) {
    docker { unpause(id: $id) { id state status } }
}
"""

MUTATION_START_VM = """
mutation StartVm($id: ID!) { vm { start(id: $id) { uuid name state } } }
"""

MUTATION_STOP_VM = """
mutation StopVm($id: ID!) { vm { stop(id: $id) { uuid name state } } }
"""

MUTATION_PAUSE_VM = """
mutation PauseVm($id: ID!) { vm { pause(id: $id) { uuid name state } } }
"""

MUTATION_RESUME_VM = """
mutation ResumeVm($id: ID!) { vm { resume(id: $id) { uuid name state } } }
"""

MUTATION_REBOOT_VM = """
mutation RebootVm($id: ID!) { vm { reboot(id: $id) { uuid name state } } }
"""

MUTATION_FORCE_STOP_VM = """
mutation ForceStopVm($id: ID!) { vm { forceStop(id: $id) { uuid name state } } }
"""

MUTATION_ARCHIVE_NOTIFICATION = """
mutation ArchiveNotification($id: ID!) { archiveNotification(id: $id) { id } }
"""

MUTATION_DELETE_NOTIFICATION = """
mutation DeleteNotification($id: ID!) { deleteNotification(id: $id) { id } }
"""

MUTATION_ARCHIVE_ALL_NOTIFICATIONS = """
mutation ArchiveAllNotifications { archiveAll { id } }
"""

# NOTE: `addUser` and `deleteUser` mutations were dropped from the Unraid API
# 4.32+ schema. If the operator needs to manage accounts they must use the
# Unraid WebGUI or the `unraid-api` CLI on the server itself.


class UnraidClient(BaseGraphQLClient):
    """Typed wrapper around the Unraid GraphQL API."""

    # ── Read methods ────────────────────────────────────────────────────

    async def get_info(self) -> SystemInfo:
        """Get system information (OS, CPU, memory, baseboard, versions)."""
        result = await self.query(QUERY_INFO)
        return SystemInfo.model_validate(result.get("info") or {})

    async def get_array(self) -> ArrayState:
        """Get array status, capacity, parity, disks, and caches."""
        result = await self.query(QUERY_ARRAY)
        return ArrayState.model_validate(result.get("array") or {})

    async def get_parity_history(self) -> list[ParityHistoryEntry]:
        """Get parity check history."""
        result = await self.query(QUERY_PARITY_HISTORY)
        history = result.get("parityHistory") or []
        if not isinstance(history, list):
            return []
        return [ParityHistoryEntry.model_validate(entry) for entry in history]

    async def list_disks(self) -> list[Disk]:
        """List all physical disks (system-wide)."""
        result = await self.query(QUERY_DISKS)
        disks = result.get("disks") or []
        if not isinstance(disks, list):
            return []
        return [Disk.model_validate(disk) for disk in disks]

    async def list_containers(self) -> list[DockerContainer]:
        """List all Docker containers."""
        result = await self.query(QUERY_DOCKER_CONTAINERS)
        containers = result.get("dockerContainers") or []
        if not isinstance(containers, list):
            return []
        return [DockerContainer.model_validate(container) for container in containers]

    async def list_docker_networks(self) -> list[DockerNetwork]:
        """List Docker networks."""
        result = await self.query(QUERY_DOCKER_NETWORKS)
        networks = result.get("dockerNetworks") or []
        if not isinstance(networks, list):
            return []
        return [DockerNetwork.model_validate(network) for network in networks]

    async def list_vms(self) -> Vms:
        """List all virtual machines."""
        result = await self.query(QUERY_VMS)
        return Vms.model_validate(result.get("vms") or {})

    async def list_shares(self) -> list[Share]:
        """List user shares."""
        result = await self.query(QUERY_SHARES)
        shares = result.get("shares") or []
        if not isinstance(shares, list):
            return []
        return [Share.model_validate(share) for share in shares]

    async def get_me(self) -> UserAccount:
        """Get the authenticated user account (the account the API key belongs to)."""
        result = await self.query(QUERY_ME)
        return UserAccount.model_validate(result.get("me") or {})

    async def list_notifications(self) -> list[Notification]:
        """List notifications."""
        result = await self.query(QUERY_NOTIFICATIONS)
        notifications = result.get("notifications") or []
        if not isinstance(notifications, list):
            return []
        return [Notification.model_validate(notification) for notification in notifications]

    async def get_flash(self) -> dict[str, Any]:
        """Get Unraid USB flash drive metadata."""
        result = await self.query(QUERY_FLASH)
        return result.get("flash", {})  # type: ignore[no-any-return]

    async def get_registration(self) -> dict[str, Any]:
        """Get Unraid registration info (license type, expiration)."""
        result = await self.query(QUERY_REGISTRATION)
        return result.get("registration", {})  # type: ignore[no-any-return]

    async def get_connect(self) -> dict[str, Any]:
        """Get Unraid Connect remote-access configuration."""
        result = await self.query(QUERY_CONNECT)
        return result.get("connect", {})  # type: ignore[no-any-return]

    # ── Write methods: array ────────────────────────────────────────────

    async def start_array(self) -> dict[str, Any]:
        """Start the array."""
        return await self.mutate(MUTATION_START_ARRAY)

    async def stop_array(self) -> dict[str, Any]:
        """Stop the array."""
        return await self.mutate(MUTATION_STOP_ARRAY)

    async def start_parity_check(self, correct: bool = False) -> dict[str, Any]:
        """Start a parity check (optionally correcting errors)."""
        return await self.mutate(MUTATION_START_PARITY_CHECK, variables={"correct": correct})

    async def pause_parity_check(self) -> dict[str, Any]:
        """Pause an in-progress parity check."""
        return await self.mutate(MUTATION_PAUSE_PARITY_CHECK)

    async def resume_parity_check(self) -> dict[str, Any]:
        """Resume a paused parity check."""
        return await self.mutate(MUTATION_RESUME_PARITY_CHECK)

    async def cancel_parity_check(self) -> dict[str, Any]:
        """Cancel an in-progress parity check."""
        return await self.mutate(MUTATION_CANCEL_PARITY_CHECK)

    # ── Write methods: docker ───────────────────────────────────────────

    async def start_container(self, container_id: str) -> dict[str, Any]:
        """Start a Docker container by ID."""
        return await self.mutate(MUTATION_START_CONTAINER, variables={"id": container_id})

    async def stop_container(self, container_id: str) -> dict[str, Any]:
        """Stop a Docker container by ID."""
        return await self.mutate(MUTATION_STOP_CONTAINER, variables={"id": container_id})

    async def restart_container(self, container_id: str) -> dict[str, Any]:
        """Restart a Docker container by ID."""
        return await self.mutate(MUTATION_RESTART_CONTAINER, variables={"id": container_id})

    async def pause_container(self, container_id: str) -> dict[str, Any]:
        """Pause a Docker container by ID."""
        return await self.mutate(MUTATION_PAUSE_CONTAINER, variables={"id": container_id})

    async def unpause_container(self, container_id: str) -> dict[str, Any]:
        """Unpause a Docker container by ID."""
        return await self.mutate(MUTATION_UNPAUSE_CONTAINER, variables={"id": container_id})

    # ── Write methods: VMs ──────────────────────────────────────────────

    async def start_vm(self, vm_id: str) -> dict[str, Any]:
        """Start a VM by UUID."""
        return await self.mutate(MUTATION_START_VM, variables={"id": vm_id})

    async def stop_vm(self, vm_id: str) -> dict[str, Any]:
        """Gracefully stop a VM by UUID."""
        return await self.mutate(MUTATION_STOP_VM, variables={"id": vm_id})

    async def pause_vm(self, vm_id: str) -> dict[str, Any]:
        """Pause a running VM by UUID."""
        return await self.mutate(MUTATION_PAUSE_VM, variables={"id": vm_id})

    async def resume_vm(self, vm_id: str) -> dict[str, Any]:
        """Resume a paused VM by UUID."""
        return await self.mutate(MUTATION_RESUME_VM, variables={"id": vm_id})

    async def reboot_vm(self, vm_id: str) -> dict[str, Any]:
        """Reboot a VM by UUID."""
        return await self.mutate(MUTATION_REBOOT_VM, variables={"id": vm_id})

    async def force_stop_vm(self, vm_id: str) -> dict[str, Any]:
        """Force-stop a VM by UUID (equivalent to pulling the plug)."""
        return await self.mutate(MUTATION_FORCE_STOP_VM, variables={"id": vm_id})

    # ── Write methods: notifications ────────────────────────────────────

    async def archive_notification(self, notification_id: str) -> dict[str, Any]:
        """Archive a notification by ID."""
        return await self.mutate(MUTATION_ARCHIVE_NOTIFICATION, variables={"id": notification_id})

    async def delete_notification(self, notification_id: str) -> dict[str, Any]:
        """Delete a notification by ID."""
        return await self.mutate(MUTATION_DELETE_NOTIFICATION, variables={"id": notification_id})

    async def archive_all_notifications(self) -> dict[str, Any]:
        """Archive all notifications."""
        return await self.mutate(MUTATION_ARCHIVE_ALL_NOTIFICATIONS)

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def validate_connection(self) -> None:
        """Validate connectivity by issuing a single short-timeout query.

        Bypasses the retry loop in :meth:`BaseGraphQLClient._post` so a
        misconfigured host fails in a few seconds instead of blocking
        startup for ``UNRAID_MAX_RETRIES * UNRAID_REQUEST_TIMEOUT`` seconds
        worst case (~90s by default).

        Raises:
            UnraidError: subclass thereof when the API is unreachable,
                unauthenticated, or returned a GraphQL error.
        """
        start = time.perf_counter()
        try:
            response = await self._client.post(
                self._graphql_url,
                json={"query": QUERY_INFO},
                timeout=httpx.Timeout(_VALIDATION_TIMEOUT_SECONDS),
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.warning("graphql validate_connection failed after %.0fms: %s", elapsed_ms, exc)
            raise UnraidConnectionError(str(exc)) from exc
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("graphql validate_connection -> HTTP %d in %.0fms", response.status_code, elapsed_ms)
        self._raise_for_status(response)
        body = self._parse_json(response)
        self._check_graphql_errors(body)
