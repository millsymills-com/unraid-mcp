"""Unraid GraphQL client with typed query and mutation methods."""

from __future__ import annotations

import logging
from typing import Any

from unraid_mcp.clients.base import BaseGraphQLClient

logger = logging.getLogger(__name__)


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

QUERY_USERS = """
query Users {
    users { id name description roles password }
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

MUTATION_CREATE_USER = """
mutation CreateUser($input: addUserInput!) {
    addUser(input: $input) { id name description }
}
"""

MUTATION_DELETE_USER = """
mutation DeleteUser($input: deleteUserInput!) {
    deleteUser(input: $input) { id name }
}
"""


class UnraidClient(BaseGraphQLClient):
    """Typed wrapper around the Unraid GraphQL API."""

    # ── Read methods ────────────────────────────────────────────────────

    async def get_info(self) -> dict[str, Any]:
        """Get system information (OS, CPU, memory, baseboard, versions)."""
        result = await self.query(QUERY_INFO)
        return result.get("info", {})  # type: ignore[no-any-return]

    async def get_array(self) -> dict[str, Any]:
        """Get array status, capacity, parity, disks, and caches."""
        result = await self.query(QUERY_ARRAY)
        return result.get("array", {})  # type: ignore[no-any-return]

    async def get_parity_history(self) -> list[dict[str, Any]]:
        """Get parity check history."""
        result = await self.query(QUERY_PARITY_HISTORY)
        history = result.get("parityHistory", [])
        return list(history) if isinstance(history, list) else []

    async def list_disks(self) -> list[dict[str, Any]]:
        """List all physical disks (system-wide)."""
        result = await self.query(QUERY_DISKS)
        disks = result.get("disks", [])
        return list(disks) if isinstance(disks, list) else []

    async def list_containers(self) -> list[dict[str, Any]]:
        """List all Docker containers."""
        result = await self.query(QUERY_DOCKER_CONTAINERS)
        containers = result.get("dockerContainers", [])
        return list(containers) if isinstance(containers, list) else []

    async def list_docker_networks(self) -> list[dict[str, Any]]:
        """List Docker networks."""
        result = await self.query(QUERY_DOCKER_NETWORKS)
        networks = result.get("dockerNetworks", [])
        return list(networks) if isinstance(networks, list) else []

    async def list_vms(self) -> dict[str, Any]:
        """List all virtual machines."""
        result = await self.query(QUERY_VMS)
        return result.get("vms", {})  # type: ignore[no-any-return]

    async def list_shares(self) -> list[dict[str, Any]]:
        """List user shares."""
        result = await self.query(QUERY_SHARES)
        shares = result.get("shares", [])
        return list(shares) if isinstance(shares, list) else []

    async def list_users(self) -> list[dict[str, Any]]:
        """List Unraid users."""
        result = await self.query(QUERY_USERS)
        users = result.get("users", [])
        return list(users) if isinstance(users, list) else []

    async def list_notifications(self) -> list[dict[str, Any]]:
        """List notifications."""
        result = await self.query(QUERY_NOTIFICATIONS)
        notifications = result.get("notifications", [])
        return list(notifications) if isinstance(notifications, list) else []

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

    # ── Write methods: users ────────────────────────────────────────────

    async def create_user(
        self,
        name: str,
        password: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create an Unraid user."""
        input_arg: dict[str, Any] = {"name": name, "password": password}
        if description is not None:
            input_arg["description"] = description
        return await self.mutate(MUTATION_CREATE_USER, variables={"input": input_arg})

    async def delete_user(self, name: str) -> dict[str, Any]:
        """Delete an Unraid user by name."""
        return await self.mutate(MUTATION_DELETE_USER, variables={"input": {"name": name}})

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def validate_connection(self) -> bool:
        """Validate connectivity by fetching basic system info."""
        try:
            await self.get_info()
        except Exception:
            logger.debug("Unraid API connection validation failed", exc_info=True)
            return False
        else:
            return True
