"""Unraid GraphQL client with typed query and mutation methods.

Schema target: Unraid API v2.x. The field contract this client depends on
is enumerated in :data:`SCHEMA_EXPECTATIONS` below, and verified at server
startup by :meth:`UnraidClient.check_schema_compatibility` (introspection
probe added in #68). Treat that dict as the source of truth — the per-query
comments here are reviewer hints, not the contract.

Drift incidents #51 and #53-#61 all shipped because the constants below
had no in-source signal about which Unraid API version a query targeted.
Before changing any ``QUERY_*`` or ``MUTATION_*`` body, update
``SCHEMA_EXPECTATIONS`` in lockstep so ``--check-schema`` keeps catching
mismatches at boot instead of at the first tool call.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from unraid_mcp.clients.base import BaseGraphQLClient
from unraid_mcp.errors import UnraidConnectionError, UnraidError
from unraid_mcp.models.array import ArrayState, ParityHistoryEntry
from unraid_mcp.models.disks import Disk
from unraid_mcp.models.docker import DockerContainer, DockerNetwork
from unraid_mcp.models.notifications import Notification
from unraid_mcp.models.shares import Share
from unraid_mcp.models.system import SystemInfo
from unraid_mcp.models.users import User
from unraid_mcp.models.vms import Vms

logger = logging.getLogger(__name__)

# Validation goes around the retry loop to fail fast on first-run typos.
_VALIDATION_TIMEOUT_SECONDS = 5


# ── Queries ─────────────────────────────────────────────────────────────

# Info / OS / CPU / memory / baseboard / versions selection sets.
# Drift history: #51 — InfoMemory and InfoVersions sub-selections didn't
# match the live schema on some Unraid builds.
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

# Array state + capacity + parity/disk/cache rosters. Stable since 2024.
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

# Parity check history rows. Stable since 2024.
QUERY_PARITY_HISTORY = """
query ParityHistory {
    parityHistory { date duration speed status errors }
}
"""

# Physical disk roster + SMART status.
# Drift history: #54 — Disk.temp was removed on newer builds; keep the
# Disk field set aligned with SCHEMA_EXPECTATIONS["Disk"].
QUERY_DISKS = """
query Disks {
    disks {
        id name device type size temp rotational interface serialNum smartStatus
    }
}
"""

# Docker container roster + port mappings.
# Drift history: #55 — root field Query.dockerContainers was missing on
# some builds; #59 (sibling write mutations) renamed scalar ID types.
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

# Docker network roster.
# Drift history: #56 — root field Query.dockerNetworks was missing on
# servers built without Docker support.
QUERY_DOCKER_NETWORKS = """
query DockerNetworks {
    dockerNetworks { id name driver scope created internal attachable ingress }
}
"""

# VM roster (single nested ``domain`` envelope). Stable since 2024 —
# sibling VM write mutations (#60) changed shape but the read path didn't.
QUERY_VMS = """
query Vms {
    vms {
        domain { uuid name state }
    }
}
"""

# User-share roster + alloc/include/exclude metadata. Stable since 2024.
QUERY_SHARES = """
query Shares {
    shares {
        name comment free size used include exclude cache nameOrig
        allocator floor splitLevel cow color luksStatus
    }
}
"""

# Unraid user accounts. NEVER select ``password`` here — leak guard in
# #107/#132. Drift history: #57 — root field Query.users was missing on
# some builds.
QUERY_USERS = """
query Users {
    users { id name description roles }
}
"""

# Notification overviews.
# Drift history: #58 — ``Notifications.type`` was removed; keep the
# selection set aligned with SCHEMA_EXPECTATIONS["Notification"].
QUERY_NOTIFICATIONS = """
query Notifications {
    notifications {
        id type title subject description importance link timestamp formattedTimestamp
    }
}
"""

# USB flash drive identity.
# Drift history: #52 — ``Flash.guid`` is non-null on the schema but the
# resolver returned null on trial/unregistered installs, causing a
# GraphQL non-null violation rather than a Pydantic-friendly empty
# result.
QUERY_FLASH = """
query Flash { flash { guid vendor product } }
"""

# License registration state. Stable since 2024.
QUERY_REGISTRATION = """
query Registration { registration { state expiration type updateExpiration } }
"""

# Unraid Connect remote-access settings.
# Drift history: #53 — ``Connect.dynamicRemoteAccessType`` was renamed,
# breaking the selection set on newer plugin versions.
QUERY_CONNECT = """
query Connect {
    connect {
        dynamicRemoteAccessType
        config { accessType forwardType port }
    }
}
"""


# ── Mutations ───────────────────────────────────────────────────────────

# Array lifecycle mutations. Stable since 2024.
MUTATION_START_ARRAY = """
mutation StartArray { startArray { state } }
"""

# Pairs with MUTATION_START_ARRAY. Stable since 2024.
MUTATION_STOP_ARRAY = """
mutation StopArray { stopArray { state } }
"""

# Parity-check lifecycle mutations (start/pause/resume/cancel). Stable
# since 2024 — all four return ``ArrayState`` and take no PrefixedID.
MUTATION_START_PARITY_CHECK = """
mutation StartParityCheck($correct: Boolean) {
    startParityCheck(correct: $correct) { state }
}
"""

# Parity pause. See MUTATION_START_PARITY_CHECK header.
MUTATION_PAUSE_PARITY_CHECK = """
mutation PauseParityCheck { pauseParityCheck { state } }
"""

# Parity resume. See MUTATION_START_PARITY_CHECK header.
MUTATION_RESUME_PARITY_CHECK = """
mutation ResumeParityCheck { resumeParityCheck { state } }
"""

# Parity cancel. See MUTATION_START_PARITY_CHECK header.
MUTATION_CANCEL_PARITY_CHECK = """
mutation CancelParityCheck { cancelParityCheck { state } }
"""

# Docker container lifecycle (start/stop/restart/pause/unpause).
# Drift history: #59 — these took ``PrefixedID!`` (not ``ID!``) on newer
# builds and the ``docker.restart`` field was removed; keep the ID type
# and the nested mutation field names aligned with the live schema.
MUTATION_START_CONTAINER = """
mutation StartContainer($id: ID!) {
    docker { start(id: $id) { id state status } }
}
"""

# Container stop. See MUTATION_START_CONTAINER header (#59).
MUTATION_STOP_CONTAINER = """
mutation StopContainer($id: ID!) {
    docker { stop(id: $id) { id state status } }
}
"""

# Container restart. See MUTATION_START_CONTAINER header (#59); the
# ``docker.restart`` field was specifically called out as removed in
# that drift report.
MUTATION_RESTART_CONTAINER = """
mutation RestartContainer($id: ID!) {
    docker { restart(id: $id) { id state status } }
}
"""

# Container pause. See MUTATION_START_CONTAINER header (#59).
MUTATION_PAUSE_CONTAINER = """
mutation PauseContainer($id: ID!) {
    docker { pause(id: $id) { id state status } }
}
"""

# Container unpause. See MUTATION_START_CONTAINER header (#59).
MUTATION_UNPAUSE_CONTAINER = """
mutation UnpauseContainer($id: ID!) {
    docker { unpause(id: $id) { id state status } }
}
"""

# VM lifecycle (start/stop/pause/resume/reboot/forceStop).
# Drift history: #60 — all six now return ``Boolean!`` on newer builds,
# making the ``{uuid name state}`` selection sets invalid. Re-verify the
# return shape against the live schema before changing any of them.
MUTATION_START_VM = """
mutation StartVm($id: ID!) { vm { start(id: $id) { uuid name state } } }
"""

# VM stop. See MUTATION_START_VM header (#60).
MUTATION_STOP_VM = """
mutation StopVm($id: ID!) { vm { stop(id: $id) { uuid name state } } }
"""

# VM pause. See MUTATION_START_VM header (#60).
MUTATION_PAUSE_VM = """
mutation PauseVm($id: ID!) { vm { pause(id: $id) { uuid name state } } }
"""

# VM resume. See MUTATION_START_VM header (#60).
MUTATION_RESUME_VM = """
mutation ResumeVm($id: ID!) { vm { resume(id: $id) { uuid name state } } }
"""

# VM reboot. See MUTATION_START_VM header (#60).
MUTATION_REBOOT_VM = """
mutation RebootVm($id: ID!) { vm { reboot(id: $id) { uuid name state } } }
"""

# VM forceStop. See MUTATION_START_VM header (#60).
MUTATION_FORCE_STOP_VM = """
mutation ForceStopVm($id: ID!) { vm { forceStop(id: $id) { uuid name state } } }
"""

# Notification archive/delete mutations.
# Drift history: #61 — ``ID!`` became ``PrefixedID!`` and
# ``NotificationOverview.id`` was removed on newer builds. Update the
# input type and the return selection in lockstep with the live schema.
MUTATION_ARCHIVE_NOTIFICATION = """
mutation ArchiveNotification($id: ID!) { archiveNotification(id: $id) { id } }
"""

# Notification delete. See MUTATION_ARCHIVE_NOTIFICATION header (#61).
MUTATION_DELETE_NOTIFICATION = """
mutation DeleteNotification($id: ID!) { deleteNotification(id: $id) { id } }
"""

# Bulk-archive of notifications. See MUTATION_ARCHIVE_NOTIFICATION
# header (#61) — same NotificationOverview.id removal risk.
MUTATION_ARCHIVE_ALL_NOTIFICATIONS = """
mutation ArchiveAllNotifications { archiveAll { id } }
"""

# Create/delete user mutations.
# NEVER select ``password`` in the return shape — server has been seen
# pushing the cleartext back; the leak guard in #107/#132 strips it from
# the model but the query itself must not request it. ``Query.users``
# itself was missing on some builds in #57, so the matching input
# types may shift in lockstep on the same upgrade.
MUTATION_CREATE_USER = """
mutation CreateUser($input: addUserInput!) {
    addUser(input: $input) { id name description }
}
"""

# Delete user. See MUTATION_CREATE_USER header (#57, #107/#132).
MUTATION_DELETE_USER = """
mutation DeleteUser($input: deleteUserInput!) {
    deleteUser(input: $input) { id name }
}
"""


# ── Schema compatibility check (#68) ────────────────────────────────────

# Fields this client reads from the Unraid GraphQL schema. Checked at
# startup via :meth:`UnraidClient.check_schema_compatibility` so drift is
# caught at boot instead of per-tool-call. Update in lockstep with the
# query/mutation constants above — the two should move together.
#
# Only the Query / Mutation root fields and a handful of nested types are
# tracked. That's deliberate: too-granular coverage turns every legit
# server-side addition into a false positive, and GraphQL is additive so
# extra fields on the server side are always safe.
SCHEMA_EXPECTATIONS: dict[str, frozenset[str]] = {
    "Query": frozenset(
        {
            "info",
            "array",
            "disks",
            "disk",
            "dockerContainers",
            "dockerNetworks",
            "vms",
            "shares",
            "users",
            "notifications",
            "flash",
            "registration",
            "connect",
            "parityHistory",
        },
    ),
    "Mutation": frozenset(
        {
            "startArray",
            "stopArray",
            "startParityCheck",
            "pauseParityCheck",
            "resumeParityCheck",
            "cancelParityCheck",
            "archiveNotification",
            "deleteNotification",
            "archiveAll",
            "addUser",
            "deleteUser",
            "docker",
            "vm",
        },
    ),
    # Top-level result types we select fields from
    "Disk": frozenset(
        {"id", "name", "device", "type", "size", "temp", "rotational", "interface", "serialNum", "smartStatus"},
    ),
    "DockerContainer": frozenset(
        {
            "id",
            "names",
            "image",
            "imageId",
            "command",
            "created",
            "state",
            "status",
            "ports",
            "autoStart",
            "networkMode",
        },
    ),
    "DockerNetwork": frozenset(
        {"id", "name", "driver", "scope", "created", "internal", "attachable", "ingress"},
    ),
    "Vms": frozenset({"domain"}),
    "VmDomain": frozenset({"uuid", "name", "state"}),
    "Notification": frozenset(
        {
            "id",
            "type",
            "title",
            "subject",
            "description",
            "importance",
            "link",
            "timestamp",
            "formattedTimestamp",
        },
    ),
    "Flash": frozenset({"guid", "vendor", "product"}),
    "Connect": frozenset({"dynamicRemoteAccessType", "config"}),
}


_INTROSPECTION_QUERY = """
query Introspect {
    __schema {
        queryType { name }
        mutationType { name }
        types { name fields { name } inputFields { name } }
    }
}
"""


async def _introspect(client: BaseGraphQLClient) -> dict[str, set[str]]:
    """Fetch the server schema and return ``{typeName: {fieldName, ...}}``."""
    result = await client.query(_INTROSPECTION_QUERY)
    schema = result.get("__schema") or {}
    types = schema.get("types") or []
    actual: dict[str, set[str]] = {}
    for t in types:
        name = t.get("name") if isinstance(t, dict) else None
        if not isinstance(name, str):
            continue
        fields = t.get("fields") or t.get("inputFields") or []
        actual[name] = {f["name"] for f in fields if isinstance(f, dict) and isinstance(f.get("name"), str)}
    return actual


def compute_schema_drift(
    expected: dict[str, frozenset[str]],
    actual: dict[str, set[str]],
) -> list[str]:
    """Return human-readable drift descriptions; empty list when schema matches.

    Each entry names the type and missing field so operators can map
    directly to the query that reads it.
    """
    drifts: list[str] = []
    for type_name, expected_fields in expected.items():
        actual_fields = actual.get(type_name)
        if actual_fields is None:
            drifts.append(
                f"{type_name}: type missing from server schema (client expects fields {sorted(expected_fields)})",
            )
            continue
        missing = expected_fields - actual_fields
        if missing:
            drifts.append(f"{type_name}: missing fields {sorted(missing)}")
    return drifts


def _require_dict(result: dict[str, Any], key: str) -> dict[str, Any]:
    """Return ``result[key]`` as a dict, raising on missing or wrong-typed values.

    A null value is normalized to an empty dict — the GraphQL contract allows
    a present-but-null field. A missing top-level key is treated as schema
    drift and raised so callers do not silently see empty results (#65).
    """
    if key not in result:
        raise UnraidError(
            f"Missing '{key}' in GraphQL response; got keys {sorted(result.keys())}. "
            "This usually means the server schema changed — run `unraid-mcp --check-schema`.",
        )
    value = result[key]
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise UnraidError(f"Expected dict for '{key}' in GraphQL response, got {type(value).__name__}")
    return value


def _require_list(result: dict[str, Any], key: str) -> list[Any]:
    """Return ``result[key]`` as a list, raising on missing or wrong-typed values.

    Null is normalized to ``[]``. Missing key is raised so schema drift is not
    silently reported as "no items" (#65).
    """
    if key not in result:
        raise UnraidError(
            f"Missing '{key}' in GraphQL response; got keys {sorted(result.keys())}. "
            "This usually means the server schema changed — run `unraid-mcp --check-schema`.",
        )
    value = result[key]
    if value is None:
        return []
    if not isinstance(value, list):
        raise UnraidError(f"Expected list for '{key}' in GraphQL response, got {type(value).__name__}")
    return value


class UnraidClient(BaseGraphQLClient):
    """Typed wrapper around the Unraid GraphQL API."""

    # ── Read methods ────────────────────────────────────────────────────

    async def get_info(self) -> SystemInfo:
        """Get system information (OS, CPU, memory, baseboard, versions)."""
        result = await self.query(QUERY_INFO)
        return SystemInfo.model_validate(_require_dict(result, "info"))

    async def get_array(self) -> ArrayState:
        """Get array status, capacity, parity, disks, and caches."""
        result = await self.query(QUERY_ARRAY)
        return ArrayState.model_validate(_require_dict(result, "array"))

    async def get_parity_history(self) -> list[ParityHistoryEntry]:
        """Get parity check history."""
        result = await self.query(QUERY_PARITY_HISTORY)
        return [ParityHistoryEntry.model_validate(entry) for entry in _require_list(result, "parityHistory")]

    async def list_disks(self) -> list[Disk]:
        """List all physical disks (system-wide)."""
        result = await self.query(QUERY_DISKS)
        return [Disk.model_validate(disk) for disk in _require_list(result, "disks")]

    async def list_containers(self) -> list[DockerContainer]:
        """List all Docker containers."""
        result = await self.query(QUERY_DOCKER_CONTAINERS)
        return [DockerContainer.model_validate(c) for c in _require_list(result, "dockerContainers")]

    async def list_docker_networks(self) -> list[DockerNetwork]:
        """List Docker networks."""
        result = await self.query(QUERY_DOCKER_NETWORKS)
        return [DockerNetwork.model_validate(n) for n in _require_list(result, "dockerNetworks")]

    async def list_vms(self) -> Vms:
        """List all virtual machines.

        Returns the ``Vms`` envelope model (``{domain: [...]}``). The wrapping
        type is set by the GraphQL schema — the list itself lives at
        ``Vms.domain``.
        """
        result = await self.query(QUERY_VMS)
        return Vms.model_validate(_require_dict(result, "vms"))

    async def list_shares(self) -> list[Share]:
        """List user shares."""
        result = await self.query(QUERY_SHARES)
        return [Share.model_validate(share) for share in _require_list(result, "shares")]

    async def list_users(self) -> list[User]:
        """List Unraid users."""
        result = await self.query(QUERY_USERS)
        return [User.model_validate(user) for user in _require_list(result, "users")]

    async def list_notifications(self) -> list[Notification]:
        """List notifications."""
        result = await self.query(QUERY_NOTIFICATIONS)
        return [Notification.model_validate(n) for n in _require_list(result, "notifications")]

    async def get_flash(self) -> dict[str, Any]:
        """Get Unraid USB flash drive metadata."""
        result = await self.query(QUERY_FLASH)
        return _require_dict(result, "flash")

    async def get_registration(self) -> dict[str, Any]:
        """Get Unraid registration info (license type, expiration)."""
        result = await self.query(QUERY_REGISTRATION)
        return _require_dict(result, "registration")

    async def get_connect(self) -> dict[str, Any]:
        """Get Unraid Connect remote-access configuration."""
        result = await self.query(QUERY_CONNECT)
        return _require_dict(result, "connect")

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

    async def check_schema_compatibility(self) -> list[str]:
        """Introspect the server schema and return drift descriptions.

        Empty list means the live schema satisfies :data:`SCHEMA_EXPECTATIONS`.
        Any mismatch (removed types, renamed fields, missing root queries) is
        reported as a string entry. Called at startup by the server lifespan
        (#68) so operators see drift in the server log rather than at the
        first tool call.

        Does not raise on drift — the server still starts. It raises the
        usual transport exceptions on connection failure so the caller can
        treat introspection the same as any other GraphQL call.
        """
        actual = await _introspect(self)
        return compute_schema_drift(SCHEMA_EXPECTATIONS, actual)

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
