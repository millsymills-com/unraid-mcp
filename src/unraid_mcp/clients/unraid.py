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
from unraid_mcp.errors import UnraidConnectionError, UnraidError, UnraidNotFoundError, UnraidValidationError
from unraid_mcp.models.array import ArrayState, ParityHistoryEntry
from unraid_mcp.models.disks import Disk
from unraid_mcp.models.docker import DockerContainer, DockerNetwork
from unraid_mcp.models.logs import LogFile, LogFileContent
from unraid_mcp.models.metrics import Metrics
from unraid_mcp.models.network import Cloud, Network
from unraid_mcp.models.notifications import Notification, NotificationImportance, NotificationType
from unraid_mcp.models.oidc import PublicOidcProvider
from unraid_mcp.models.plugins import Plugin, PluginInstallOperation
from unraid_mcp.models.rclone import RCloneConfig
from unraid_mcp.models.settings import ApiSettings, DisplaySettings, Service
from unraid_mcp.models.shares import Share
from unraid_mcp.models.system import SystemInfo
from unraid_mcp.models.system_time import SystemTime, TimeZoneOption
from unraid_mcp.models.ups import UPSConfiguration, UPSDevice
from unraid_mcp.models.users import User
from unraid_mcp.models.vars import Vars
from unraid_mcp.models.vms import Vms

logger = logging.getLogger(__name__)

# Validation goes around the retry loop to fail fast on first-run typos.
_VALIDATION_TIMEOUT_SECONDS = 5


# ── Queries ─────────────────────────────────────────────────────────────

# Info / OS / CPU / memory / baseboard / versions selection sets.
# Drift history: #51 — InfoMemory lost its aggregated totals in favor of
# per-DIMM ``layout`` entries, and InfoVersions was regrouped into
# ``core`` / ``packages`` on Unraid API 4.32+. Keep the selection set
# aligned with SCHEMA_EXPECTATIONS["InfoMemory"] / ["InfoVersions"].
QUERY_INFO = """
query Info {
    info {
        id
        os { platform distro release codename kernel arch hostname uptime }
        cpu { manufacturer brand vendor family model stepping speed cores threads processors }
        memory {
            id
            layout { size type clockSpeed formFactor manufacturer partNum serialNum bank }
        }
        baseboard { manufacturer model version serial }
        versions {
            id
            core { unraid kernel api }
            packages { openssl docker node npm nginx php git pm2 }
        }
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
# Drift history: #54 — on Unraid API 4.32+ ``Disk.temp`` was renamed to
# ``temperature``, ``Disk.interface`` to ``interfaceType``, ``rotational``
# was removed (closest live equivalent is the inverse of ``isSpinning``).
# Keep the Disk field set aligned with SCHEMA_EXPECTATIONS["Disk"].
QUERY_DISKS = """
query Disks {
    disks {
        id name device type vendor size temperature interfaceType serialNum smartStatus isSpinning
    }
}
"""

# Single physical disk by ID — O(1) on schemas that expose ``Query.disk``
# (Unraid API 4.32+). Same field set as :data:`QUERY_DISKS` so callers see
# the same shape regardless of which path served the lookup. Falls back to
# list-then-filter at the client method level when the server rejects the
# query with ``GRAPHQL_VALIDATION_FAILED``, so older schemas keep working
# without a flag. ``$id`` is ``PrefixedID!`` to match ``Disk.id``.
QUERY_DISK_BY_ID = """
query DiskById($id: PrefixedID!) {
    disk(id: $id) {
        id name device type vendor size temperature interfaceType serialNum smartStatus isSpinning
    }
}
"""

# Docker container roster + port mappings.
# Drift history: #55 — top-level ``Query.dockerContainers`` was removed
# in favor of a grouped ``docker.containers`` shape on Unraid API 4.32+,
# and ``DockerContainer.networkMode`` no longer exists; #59 (sibling
# write mutations) renamed scalar ID types.
QUERY_DOCKER_CONTAINERS = """
query DockerContainers {
    docker {
        containers {
            id names image imageId command created state status
            autoStart
            ports { ip privatePort publicPort type }
        }
    }
}
"""

# Single Docker container by ID — O(1) on schemas that expose
# ``Docker.container`` (Unraid API 4.32+). Same field set as the list
# variant so callers see the same shape regardless of which path served
# the lookup. The client falls back to list-then-filter on
# ``GRAPHQL_VALIDATION_FAILED`` so older schemas keep working.
QUERY_CONTAINER_BY_ID = """
query ContainerById($id: PrefixedID!) {
    docker {
        container(id: $id) {
            id names image imageId command created state status
            autoStart
            ports { ip privatePort publicPort type }
        }
    }
}
"""

# Docker network roster.
# Drift history: #56 — top-level ``Query.dockerNetworks`` was removed in
# favor of ``docker.networks`` on Unraid API 4.32+, mirroring the same
# regrouping that hit ``Query.dockerContainers`` in #55.
QUERY_DOCKER_NETWORKS = """
query DockerNetworks {
    docker {
        networks { id name driver scope created internal attachable ingress enableIPv6 }
    }
}
"""

# VM roster (single nested ``domain`` envelope). Stable since 2024 —
# sibling VM write mutations (#60) changed shape but the read path didn't.
QUERY_VMS = """
query Vms {
    vms {
        domain { id name state }
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

# Currently-authenticated Unraid user account. NEVER select ``password``
# here — leak guard in #107/#132. Drift history: #57 — ``Query.users``,
# ``addUser`` and ``deleteUser`` were removed in Unraid 7.2+; ``Query.me``
# (returning a ``UserAccount``) is what replaces the list-and-mutate surface.
QUERY_ME = """
query Me {
    me { id name description roles }
}
"""

# Notification overviews.
# Drift history: #58 — on Unraid API 4.32+ the ``Notifications`` wrapper
# lost its top-level ``type`` field and entries now live under
# ``.list(filter: NotificationFilter)``. ``NotificationFilter.type`` is
# required, so callers must pick UNREAD or ARCHIVE; ``limit`` and
# ``offset`` round out the pagination cursor. Keep the entry-level
# selection aligned with SCHEMA_EXPECTATIONS["Notification"].
QUERY_NOTIFICATIONS = """
query Notifications($type: NotificationType!, $limit: Int!, $offset: Int!) {
    notifications {
        id
        list(filter: { type: $type, limit: $limit, offset: $offset }) {
            id type title subject description importance link timestamp formattedTimestamp
        }
    }
}
"""

# USB flash drive identity.
# Drift history: #52 — ``Flash.guid`` is non-null on the schema but the
# resolver returns null on trial/unregistered installs, blowing up the
# whole response with a GraphQL non-null violation. ``guid`` is no
# longer selected; the field stays in the schema and can be re-added
# once the upstream resolver is fixed.
QUERY_FLASH = """
query Flash { flash { vendor product } }
"""

# License registration state. Stable since 2024.
QUERY_REGISTRATION = """
query Registration { registration { state expiration type updateExpiration } }
"""

# Unraid Connect remote-access settings.
# Drift history: #53 — on Unraid API 4.32+ ``Connect.dynamicRemoteAccessType``
# became a nested ``dynamicRemoteAccess { enabledType runningType error }``
# object, and the legacy ``config { accessType forwardType port }`` fields
# moved to the sibling top-level ``remoteAccess`` query. Both are fetched
# in one round-trip so :meth:`UnraidClient.get_connect` can return a
# combined shape.
QUERY_CONNECT = """
query Connect {
    connect {
        id
        dynamicRemoteAccess { enabledType runningType error }
    }
    remoteAccess { accessType forwardType port }
}
"""

# System metrics snapshot (CPU / memory / temperature).
# ``cpu``/``memory``/``temperature`` are all nullable. ``temperature.sensors``
# is selected without ``history`` — that array is unbounded and belongs to the
# streaming subscription, not this snapshot. Keep aligned with
# SCHEMA_EXPECTATIONS["Metrics"] / ["CpuUtilization"] / ["MemoryUtilization"] /
# ["TemperatureMetrics"] / ["TemperatureSensor"] / ["TemperatureSummary"].
QUERY_METRICS = """
query Metrics {
    metrics {
        cpu { percentTotal cpus { percentTotal } }
        memory {
            total used free available active buffcache percentTotal
            swapTotal swapUsed swapFree percentSwapTotal
        }
        temperature {
            summary {
                average warningCount criticalCount
                hottest { name type location current { value unit status } }
                coolest { name type location current { value unit status } }
            }
            sensors {
                name type location warning critical
                current { value unit status }
                min { value unit status }
                max { value unit status }
            }
        }
    }
}
"""

# UPS device roster, single device lookup, and monitoring configuration.
QUERY_UPS_DEVICES = """
query UpsDevices {
    upsDevices {
        id name model status
        battery { chargeLevel estimatedRuntime health }
        power { inputVoltage outputVoltage loadPercentage nominalPower currentPower }
    }
}
"""

# Single UPS device by ID (nullable — null when no match).
QUERY_UPS_DEVICE_BY_ID = """
query UpsDeviceById($id: String!) {
    upsDeviceById(id: $id) {
        id name model status
        battery { chargeLevel estimatedRuntime health }
        power { inputVoltage outputVoltage loadPercentage nominalPower currentPower }
    }
}
"""

# UPS monitoring configuration (apcupsd-style settings).
QUERY_UPS_CONFIGURATION = """
query UpsConfiguration {
    upsConfiguration {
        service upsCable customUpsCable upsType device overrideUpsCapacity
        batteryLevel minutes timeout killUps nisIp netServer upsName modelName
    }
}
"""

# Installed plugin inventory with metadata.
QUERY_PLUGINS = """
query Plugins {
    plugins { name version hasApiModule hasCliModule }
}
"""

# Installed Unraid OS plugins by .plg filename (list of strings).
QUERY_INSTALLED_UNRAID_PLUGINS = """
query InstalledUnraidPlugins { installedUnraidPlugins }
"""

# Tracked plugin install operations.
QUERY_PLUGIN_INSTALL_OPERATIONS = """
query PluginInstallOperations {
    pluginInstallOperations { id url name status createdAt updatedAt finishedAt output }
}
"""

# Single plugin install operation by id (nullable).
QUERY_PLUGIN_INSTALL_OPERATION = """
query PluginInstallOperation($operationId: ID!) {
    pluginInstallOperation(operationId: $operationId) {
        id url name status createdAt updatedAt finishedAt output
    }
}
"""

# Available log files (name / path / size / mtime).
QUERY_LOG_FILES = """
query LogFiles {
    logFiles { name path size modifiedAt }
}
"""

# Log file contents with optional paging (lines / startLine).
QUERY_LOG_FILE = """
query LogFile($path: String!, $lines: Int, $startLine: Int) {
    logFile(path: $path, lines: $lines, startLine: $startLine) {
        path content totalLines startLine
    }
}
"""

# Whether single-sign-on is enabled (boolean).
QUERY_SSO_STATUS = """
query SsoStatus { isSSOEnabled }
"""

# Public OIDC providers for login buttons. Secret-free projection — never
# select ``OidcProvider`` (it carries ``clientSecret``).
QUERY_PUBLIC_OIDC_PROVIDERS = """
query PublicOidcProviders {
    publicOidcProviders { id name buttonText buttonIcon buttonVariant buttonStyle }
}
"""

# Network access URLs.
QUERY_NETWORK = """
query Network {
    network { id accessUrls { type name ipv4 ipv6 } }
}
"""

# Unraid Connect cloud health. ``apiKey`` is reduced to ``{valid error}`` —
# the key material itself is never selected (PROTO-012).
QUERY_CLOUD = """
query Cloud {
    cloud {
        error
        apiKey { valid error }
        relay { status timeout error }
        minigraphql { status timeout error }
        cloud { status ip error }
        allowedOrigins
    }
}
"""

# Background services roster.
QUERY_SERVICES = """
query Services {
    services { id name online uptime { timestamp } version }
}
"""

# Display settings. ``case.base64`` is intentionally not selected — it is a
# large image blob with no agent value (default-omit per plan §3).
QUERY_DISPLAY = """
query Display {
    display {
        id
        case { url icon error }
        theme unit scale tabs resize wwn total usage text
        warning critical hot max locale
    }
}
"""

# API settings (``settings.api`` branch only — skip the ``unified``/``sso``
# JSON form blobs).
QUERY_API_SETTINGS = """
query ApiSettings {
    settings { id api { version extraOrigins sandbox plugins } }
}
"""

# Current system time configuration.
QUERY_SYSTEM_TIME = """
query SystemTime {
    systemTime { currentTime timeZone useNtp ntpServers }
}
"""

# Available IANA timezone options.
QUERY_TIMEZONE_OPTIONS = """
query TimeZoneOptions {
    timeZoneOptions { value label }
}
"""

# Curated Unraid system variables. ``csrfToken`` is intentionally never
# selected (PROTO-012) — it is a session secret.
QUERY_VARS = """
query Vars {
    vars {
        id version name timeZone comment workgroup domain
        sysModel sysArraySlots sysCacheSlots sysFlashSlots
        useSsl port portssl useSsh portssh useTelnet useNtp
        ntpServer1 ntpServer2 ntpServer3 ntpServer4
        startArray spindownDelay defaultFormat defaultFsType
        shareCount shareSmbCount shareNfsCount shareAfpCount
        deviceCount mdNumDisks mdState fsState regState regTy
        flashProduct flashVendor configValid safeMode
    }
}
"""

# Disks eligible for assignment to the array (reuses the Disk field set).
QUERY_ASSIGNABLE_DISKS = """
query AssignableDisks {
    assignableDisks {
        id name device type vendor size temperature interfaceType serialNum smartStatus isSpinning
    }
}
"""

# Rclone backup configuration. ``RCloneRemote.parameters``/``config`` are JSON
# blobs that may carry cloud credentials and are deliberately NOT selected
# (PROTO-012). ``configForm`` is skipped (UI form schema, no agent value).
QUERY_RCLONE_CONFIG = """
query RcloneConfig {
    rclone {
        remotes { name type }
        drives { name }
    }
}
"""


# ── Mutations ───────────────────────────────────────────────────────────

# Array lifecycle mutations.
# Drift history: root-level ``startArray`` / ``stopArray`` were removed
# in favor of ``array.setState(input: {desiredState: START | STOP})``
# on Unraid API 4.32+. The return shape is the same ``ArrayState`` —
# select ``state`` to keep the response useful to callers.
MUTATION_START_ARRAY = """
mutation StartArray {
    array { setState(input: { desiredState: START }) { state } }
}
"""

# Pairs with MUTATION_START_ARRAY. Same regrouping (see header).
MUTATION_STOP_ARRAY = """
mutation StopArray {
    array { setState(input: { desiredState: STOP }) { state } }
}
"""

# Parity-check lifecycle mutations (start/pause/resume/cancel).
# Drift history: root-level ``startParityCheck`` / ``pauseParityCheck``
# / ``resumeParityCheck`` / ``cancelParityCheck`` were removed in favor
# of the grouped ``parityCheck.{start,pause,resume,cancel}`` shape on
# Unraid API 4.32+. The grouped fields return a JSON-ish payload (no
# typed selection set), so the mutation bodies have no inner braces.
MUTATION_START_PARITY_CHECK = """
mutation StartParityCheck($correct: Boolean!) {
    parityCheck { start(correct: $correct) }
}
"""

# Parity pause. See MUTATION_START_PARITY_CHECK header.
MUTATION_PAUSE_PARITY_CHECK = """
mutation PauseParityCheck { parityCheck { pause } }
"""

# Parity resume. See MUTATION_START_PARITY_CHECK header.
MUTATION_RESUME_PARITY_CHECK = """
mutation ResumeParityCheck { parityCheck { resume } }
"""

# Parity cancel. See MUTATION_START_PARITY_CHECK header.
MUTATION_CANCEL_PARITY_CHECK = """
mutation CancelParityCheck { parityCheck { cancel } }
"""

# Docker container lifecycle (start/stop/pause/unpause).
# Drift history: #59 — these take ``PrefixedID!`` (not ``ID!``) on
# Unraid API 4.32+, and the ``docker.restart`` field was removed
# entirely. The client now reimplements ``restart_container`` as a
# client-side stop → start sequence; there's no matching mutation
# constant for it anymore.
MUTATION_START_CONTAINER = """
mutation StartContainer($id: PrefixedID!) {
    docker { start(id: $id) { id state status } }
}
"""

# Container stop. See MUTATION_START_CONTAINER header (#59).
MUTATION_STOP_CONTAINER = """
mutation StopContainer($id: PrefixedID!) {
    docker { stop(id: $id) { id state status } }
}
"""

# Container pause. See MUTATION_START_CONTAINER header (#59).
MUTATION_PAUSE_CONTAINER = """
mutation PauseContainer($id: PrefixedID!) {
    docker { pause(id: $id) { id state status } }
}
"""

# Container unpause. See MUTATION_START_CONTAINER header (#59).
MUTATION_UNPAUSE_CONTAINER = """
mutation UnpauseContainer($id: PrefixedID!) {
    docker { unpause(id: $id) { id state status } }
}
"""

# VM lifecycle (start/stop/pause/resume/reboot/forceStop).
# Drift history: #60 — all six return ``Boolean!`` on Unraid API 4.32+,
# making the legacy ``{uuid name state}`` selection sets invalid; the
# selection sets are dropped and ``$id`` is typed as ``PrefixedID!``.
# The matching client methods normalise the response to
# ``{"ok": bool, "id": vm_id}`` because there is no domain object to
# return.
MUTATION_START_VM = """
mutation StartVm($id: PrefixedID!) { vm { start(id: $id) } }
"""

# VM stop. See MUTATION_START_VM header (#60).
MUTATION_STOP_VM = """
mutation StopVm($id: PrefixedID!) { vm { stop(id: $id) } }
"""

# VM pause. See MUTATION_START_VM header (#60).
MUTATION_PAUSE_VM = """
mutation PauseVm($id: PrefixedID!) { vm { pause(id: $id) } }
"""

# VM resume. See MUTATION_START_VM header (#60).
MUTATION_RESUME_VM = """
mutation ResumeVm($id: PrefixedID!) { vm { resume(id: $id) } }
"""

# VM reboot. See MUTATION_START_VM header (#60).
MUTATION_REBOOT_VM = """
mutation RebootVm($id: PrefixedID!) { vm { reboot(id: $id) } }
"""

# VM forceStop. See MUTATION_START_VM header (#60).
MUTATION_FORCE_STOP_VM = """
mutation ForceStopVm($id: PrefixedID!) { vm { forceStop(id: $id) } }
"""

# Notification archive/delete/bulk-archive mutations.
# Drift history: #61 — ``ID!`` became ``PrefixedID!``;
# ``deleteNotification`` gained a required ``type: NotificationType!``
# argument so the server knows which counter to decrement.
# Drift #176 (live_write coverage): ``archiveNotification`` now returns
# the archived ``Notification`` (not the ``NotificationOverview``);
# ``archiveAll(importance: ...)`` was removed and its replacement
# ``archiveNotifications(ids: [PrefixedID!]!)`` takes explicit IDs and
# returns ``NotificationOverview``.
MUTATION_ARCHIVE_NOTIFICATION = """
mutation ArchiveNotification($id: PrefixedID!) {
    archiveNotification(id: $id) {
        id type title importance timestamp
    }
}
"""

# Notification delete. See MUTATION_ARCHIVE_NOTIFICATION header.
MUTATION_DELETE_NOTIFICATION = """
mutation DeleteNotification($id: PrefixedID!, $type: NotificationType!) {
    deleteNotification(id: $id, type: $type) {
        unread { total info warning alert }
        archive { total info warning alert }
    }
}
"""

# Bulk-archive of notifications by ID. See MUTATION_ARCHIVE_NOTIFICATION
# header for the schema migration that introduced this shape.
MUTATION_ARCHIVE_NOTIFICATIONS = """
mutation ArchiveNotifications($ids: [PrefixedID!]!) {
    archiveNotifications(ids: $ids) {
        unread { total info warning alert }
        archive { total info warning alert }
    }
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
            "docker",
            "vms",
            "shares",
            "me",
            "notifications",
            "flash",
            "registration",
            "connect",
            "remoteAccess",
            "parityHistory",
            "metrics",
            "upsDevices",
            "upsDeviceById",
            "upsConfiguration",
            "plugins",
            "installedUnraidPlugins",
            "pluginInstallOperations",
            "pluginInstallOperation",
            "logFiles",
            "logFile",
            "isSSOEnabled",
            "publicOidcProviders",
            "network",
            "cloud",
            "services",
            "display",
            "settings",
            "systemTime",
            "timeZoneOptions",
            "vars",
            "assignableDisks",
            "rclone",
        },
    ),
    "Mutation": frozenset(
        {
            "array",
            "parityCheck",
            "archiveNotification",
            "deleteNotification",
            "archiveNotifications",
            "docker",
            "vm",
        },
    ),
    "ArrayMutations": frozenset({"setState"}),
    "ParityCheckMutations": frozenset({"start", "pause", "resume", "cancel"}),
    "DockerMutations": frozenset({"start", "stop", "pause", "unpause"}),
    "VmMutations": frozenset({"start", "stop", "pause", "resume", "reboot", "forceStop"}),
    # Top-level result types we select fields from
    "Disk": frozenset(
        {
            "id",
            "name",
            "device",
            "type",
            "vendor",
            "size",
            "temperature",
            "interfaceType",
            "serialNum",
            "smartStatus",
            "isSpinning",
        },
    ),
    "Docker": frozenset({"containers", "container", "networks"}),
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
        },
    ),
    "DockerNetwork": frozenset(
        {"id", "name", "driver", "scope", "created", "internal", "attachable", "ingress", "enableIPv6"},
    ),
    "Vms": frozenset({"domain"}),
    "VmDomain": frozenset({"id", "name", "state"}),
    "Notifications": frozenset({"id", "list"}),
    "NotificationOverview": frozenset({"unread", "archive"}),
    "NotificationCounts": frozenset({"total", "info", "warning", "alert"}),
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
    "Flash": frozenset({"vendor", "product"}),
    "Connect": frozenset({"id", "dynamicRemoteAccess"}),
    "DynamicRemoteAccessStatus": frozenset({"enabledType", "runningType", "error"}),
    "RemoteAccess": frozenset({"accessType", "forwardType", "port"}),
    "InfoMemory": frozenset({"id", "layout"}),
    "MemoryLayout": frozenset(
        {"size", "type", "clockSpeed", "formFactor", "manufacturer", "partNum", "serialNum", "bank"},
    ),
    "InfoVersions": frozenset({"id", "core", "packages"}),
    "CoreVersions": frozenset({"unraid", "kernel", "api"}),
    "PackageVersions": frozenset({"openssl", "docker", "node", "npm", "nginx", "php", "git", "pm2"}),
    # ── Phase-1 read-coverage leaf types ────────────────────────────────
    "Metrics": frozenset({"cpu", "memory", "temperature"}),
    "CpuUtilization": frozenset({"percentTotal", "cpus"}),
    "CpuLoad": frozenset({"percentTotal"}),
    "MemoryUtilization": frozenset(
        {
            "total",
            "used",
            "free",
            "available",
            "active",
            "buffcache",
            "percentTotal",
            "swapTotal",
            "swapUsed",
            "swapFree",
            "percentSwapTotal",
        },
    ),
    "TemperatureMetrics": frozenset({"sensors", "summary"}),
    "TemperatureSummary": frozenset({"average", "hottest", "coolest", "warningCount", "criticalCount"}),
    "TemperatureSensor": frozenset(
        {"name", "type", "location", "current", "min", "max", "warning", "critical"},
    ),
    "TemperatureReading": frozenset({"value", "unit", "status"}),
    "UPSDevice": frozenset({"id", "name", "model", "status", "battery", "power"}),
    "UPSBattery": frozenset({"chargeLevel", "estimatedRuntime", "health"}),
    "UPSPower": frozenset(
        {"inputVoltage", "outputVoltage", "loadPercentage", "nominalPower", "currentPower"},
    ),
    "UPSConfiguration": frozenset(
        {
            "service",
            "upsCable",
            "customUpsCable",
            "upsType",
            "device",
            "overrideUpsCapacity",
            "batteryLevel",
            "minutes",
            "timeout",
            "killUps",
            "nisIp",
            "netServer",
            "upsName",
            "modelName",
        },
    ),
    "Plugin": frozenset({"name", "version", "hasApiModule", "hasCliModule"}),
    "PluginInstallOperation": frozenset(
        {"id", "url", "name", "status", "createdAt", "updatedAt", "finishedAt", "output"},
    ),
    "LogFile": frozenset({"name", "path", "size", "modifiedAt"}),
    "LogFileContent": frozenset({"path", "content", "totalLines", "startLine"}),
    "PublicOidcProvider": frozenset(
        {"id", "name", "buttonText", "buttonIcon", "buttonVariant", "buttonStyle"},
    ),
    "Network": frozenset({"id", "accessUrls"}),
    "AccessUrl": frozenset({"type", "name", "ipv4", "ipv6"}),
    "Cloud": frozenset({"error", "apiKey", "relay", "minigraphql", "cloud", "allowedOrigins"}),
    "ApiKeyResponse": frozenset({"valid", "error"}),
    "RelayResponse": frozenset({"status", "timeout", "error"}),
    "MinigraphqlResponse": frozenset({"status", "timeout", "error"}),
    "CloudResponse": frozenset({"status", "ip", "error"}),
    "Service": frozenset({"id", "name", "online", "uptime", "version"}),
    "Uptime": frozenset({"timestamp"}),
    "InfoDisplay": frozenset(
        {
            "id",
            "case",
            "theme",
            "unit",
            "scale",
            "tabs",
            "resize",
            "wwn",
            "total",
            "usage",
            "text",
            "warning",
            "critical",
            "hot",
            "max",
            "locale",
        },
    ),
    "InfoDisplayCase": frozenset({"url", "icon", "error"}),
    "Settings": frozenset({"id", "api"}),
    "ApiConfig": frozenset({"version", "extraOrigins", "sandbox", "plugins"}),
    "SystemTime": frozenset({"currentTime", "timeZone", "useNtp", "ntpServers"}),
    "TimeZoneOption": frozenset({"value", "label"}),
    "Vars": frozenset(
        {
            "id",
            "version",
            "name",
            "timeZone",
            "comment",
            "workgroup",
            "domain",
            "sysModel",
            "sysArraySlots",
            "sysCacheSlots",
            "sysFlashSlots",
            "useSsl",
            "port",
            "portssl",
            "useSsh",
            "portssh",
            "useTelnet",
            "useNtp",
            "ntpServer1",
            "ntpServer2",
            "ntpServer3",
            "ntpServer4",
            "startArray",
            "spindownDelay",
            "defaultFormat",
            "defaultFsType",
            "shareCount",
            "shareSmbCount",
            "shareNfsCount",
            "shareAfpCount",
            "deviceCount",
            "mdNumDisks",
            "mdState",
            "fsState",
            "regState",
            "regTy",
            "flashProduct",
            "flashVendor",
            "configValid",
            "safeMode",
        },
    ),
    "RCloneBackupSettings": frozenset({"remotes", "drives"}),
    "RCloneRemote": frozenset({"name", "type"}),
    "RCloneDrive": frozenset({"name"}),
}


_INTROSPECTION_QUERY = """
query Introspect {
    __schema {
        queryType { name }
        mutationType { name }
        types { name fields(includeDeprecated: true) { name } inputFields { name } }
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

    async def get_disk(self, disk_id: str) -> Disk:
        """Get a single physical disk by ID or name.

        Issues the O(1) ``Query.disk(id:)`` singular query on Unraid API
        4.32+ schemas; on validation failure (older schemas without the
        singular field) falls back to :meth:`list_disks` + linear scan.
        Both paths raise :class:`UnraidNotFoundError` when no disk matches.

        ``Query.disk`` is keyed on ``Disk.id`` only. The fallback path also
        matches against ``Disk.name`` for parity with the legacy tool
        behaviour, so callers can keep passing either identifier.
        """
        try:
            result = await self.query(QUERY_DISK_BY_ID, variables={"id": disk_id})
        except UnraidValidationError:
            return self._find_disk_in_list(await self.list_disks(), disk_id)
        disk = result.get("disk")
        if disk is None:
            return self._find_disk_in_list(await self.list_disks(), disk_id)
        if not isinstance(disk, dict):
            raise UnraidError(f"Expected dict for 'disk' in GraphQL response, got {type(disk).__name__}")
        return Disk.model_validate(disk)

    @staticmethod
    def _find_disk_in_list(disks: list[Disk], disk_id: str) -> Disk:
        for disk in disks:
            if disk_id in (disk.id, disk.name):
                return disk
        raise UnraidNotFoundError(f"Disk with id '{disk_id}' not found")

    async def list_containers(self) -> list[DockerContainer]:
        """List all Docker containers.

        On Unraid API 4.32+ the field group lives at ``docker.containers``;
        a present-but-null ``docker`` (Docker daemon unreachable on the
        server) normalises to an empty list rather than raising — schema
        drift only fires when the top-level ``docker`` key is missing.
        """
        result = await self.query(QUERY_DOCKER_CONTAINERS)
        docker = _require_dict(result, "docker")
        containers = docker.get("containers")
        if containers is None:
            return []
        if not isinstance(containers, list):
            raise UnraidError(
                f"Expected list for 'docker.containers' in GraphQL response, got {type(containers).__name__}",
            )
        return [DockerContainer.model_validate(c) for c in containers]

    async def get_container(self, container_id: str) -> DockerContainer:
        """Get a single Docker container by ID or name.

        Issues the O(1) ``Docker.container(id:)`` singular query on Unraid
        API 4.32+ schemas; on validation failure (older schemas without the
        singular field) falls back to :meth:`list_containers` + linear scan.
        Both paths raise :class:`UnraidNotFoundError` when no container
        matches.

        ``Docker.container`` is keyed on ``DockerContainer.id`` only. The
        fallback path also matches against the ``names`` array (with leading
        slashes stripped) for parity with the legacy tool behaviour, so
        callers can keep passing either an ID or a container name.
        """
        try:
            result = await self.query(QUERY_CONTAINER_BY_ID, variables={"id": container_id})
        except UnraidValidationError:
            return self._find_container_in_list(await self.list_containers(), container_id)
        docker = result.get("docker")
        if not isinstance(docker, dict):
            return self._find_container_in_list(await self.list_containers(), container_id)
        container = docker.get("container")
        if container is None:
            return self._find_container_in_list(await self.list_containers(), container_id)
        if not isinstance(container, dict):
            raise UnraidError(
                f"Expected dict for 'docker.container' in GraphQL response, got {type(container).__name__}",
            )
        return DockerContainer.model_validate(container)

    @staticmethod
    def _find_container_in_list(containers: list[DockerContainer], container_id: str) -> DockerContainer:
        target = container_id.lstrip("/")
        for container in containers:
            if container.id == container_id:
                return container
            names = container.names or []
            if any(name.lstrip("/") == target for name in names):
                return container
        raise UnraidNotFoundError(f"Container '{container_id}' not found")

    async def list_docker_networks(self) -> list[DockerNetwork]:
        """List Docker networks.

        On Unraid API 4.32+ the field group lives at ``docker.networks``;
        same null-tolerance behaviour as :meth:`list_containers`.
        """
        result = await self.query(QUERY_DOCKER_NETWORKS)
        docker = _require_dict(result, "docker")
        networks = docker.get("networks")
        if networks is None:
            return []
        if not isinstance(networks, list):
            raise UnraidError(
                f"Expected list for 'docker.networks' in GraphQL response, got {type(networks).__name__}",
            )
        return [DockerNetwork.model_validate(n) for n in networks]

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

    async def get_share(self, name: str) -> Share:
        """Get a single user share by name.

        The live Unraid GraphQL schema does not expose a singular ``share``
        query (only ``shares``), so this method always lists and filters.
        Kept on the client surface for symmetry with :meth:`get_disk` and
        :meth:`get_container` and so the tool layer can call it without
        leaking the list-and-scan detail.
        """
        for share in await self.list_shares():
            if share.name == name:
                return share
        raise UnraidNotFoundError(f"Share '{name}' not found")

    async def get_me(self) -> User:
        """Get the currently-authenticated Unraid user account.

        Replaces the removed ``list_users`` on Unraid 7.2+, where
        ``Query.users`` no longer exists. ``Query.me`` returns the
        single ``UserAccount`` matching the API key in use.
        """
        result = await self.query(QUERY_ME)
        return User.model_validate(_require_dict(result, "me"))

    async def list_notifications(
        self,
        notification_type: NotificationType = "UNREAD",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """List notifications (paginated via the server-side filter).

        On Unraid API 4.32+ ``notifications.list`` is the entry list and
        the wrapper requires a ``NotificationFilter`` argument — callers
        pick ``UNREAD`` or ``ARCHIVE`` to choose which bin to read.

        Args:
            notification_type: ``UNREAD`` (default) or ``ARCHIVE``.
            limit: Maximum entries to return.
            offset: Pagination offset.
        """
        result = await self.query(
            QUERY_NOTIFICATIONS,
            variables={"type": notification_type, "limit": limit, "offset": offset},
        )
        notifications = _require_dict(result, "notifications")
        entries = notifications.get("list")
        if entries is None:
            return []
        if not isinstance(entries, list):
            raise UnraidError(
                f"Expected list for 'notifications.list' in GraphQL response, got {type(entries).__name__}",
            )
        return [Notification.model_validate(n) for n in entries]

    async def get_flash(self) -> dict[str, Any]:
        """Get Unraid USB flash drive metadata."""
        result = await self.query(QUERY_FLASH)
        return _require_dict(result, "flash")

    async def get_registration(self) -> dict[str, Any]:
        """Get Unraid registration info (license type, expiration)."""
        result = await self.query(QUERY_REGISTRATION)
        return _require_dict(result, "registration")

    async def get_connect(self) -> dict[str, Any]:
        """Get Unraid Connect remote-access configuration.

        Merges the live schema's ``connect { dynamicRemoteAccess }`` object
        with the sibling top-level ``remoteAccess { accessType forwardType port }``
        query so callers see one combined shape under the legacy ``connect``
        key.
        """
        result = await self.query(QUERY_CONNECT)
        connect = _require_dict(result, "connect")
        remote_access = result.get("remoteAccess") or {}
        return {**connect, "remoteAccess": remote_access}

    # ── Read methods: metrics ───────────────────────────────────────────

    async def get_metrics(self) -> Metrics:
        """Get the current CPU / memory / temperature metrics snapshot.

        The unbounded ``temperature.sensors[].history`` array is not selected —
        it belongs to the streaming subscription, not this snapshot.
        """
        result = await self.query(QUERY_METRICS)
        return Metrics.model_validate(_require_dict(result, "metrics"))

    # ── Read methods: UPS ───────────────────────────────────────────────

    async def list_ups_devices(self) -> list[UPSDevice]:
        """List all monitored UPS devices."""
        result = await self.query(QUERY_UPS_DEVICES)
        return [UPSDevice.model_validate(d) for d in _require_list(result, "upsDevices")]

    async def get_ups_device(self, device_id: str) -> UPSDevice:
        """Get a single UPS device by ID.

        Raises:
            UnraidNotFoundError: when no device matches ``device_id``.
        """
        result = await self.query(QUERY_UPS_DEVICE_BY_ID, variables={"id": device_id})
        device = result.get("upsDeviceById")
        if device is None:
            raise UnraidNotFoundError(f"UPS device with id '{device_id}' not found")
        if not isinstance(device, dict):
            raise UnraidError(f"Expected dict for 'upsDeviceById', got {type(device).__name__}")
        return UPSDevice.model_validate(device)

    async def get_ups_configuration(self) -> UPSConfiguration:
        """Get the UPS monitoring service configuration."""
        result = await self.query(QUERY_UPS_CONFIGURATION)
        return UPSConfiguration.model_validate(_require_dict(result, "upsConfiguration"))

    # ── Read methods: plugins ───────────────────────────────────────────

    async def list_plugins(self) -> list[Plugin]:
        """List all installed plugins with their metadata."""
        result = await self.query(QUERY_PLUGINS)
        return [Plugin.model_validate(p) for p in _require_list(result, "plugins")]

    async def list_installed_unraid_plugins(self) -> list[str]:
        """List installed Unraid OS plugins by ``.plg`` filename."""
        result = await self.query(QUERY_INSTALLED_UNRAID_PLUGINS)
        return [str(name) for name in _require_list(result, "installedUnraidPlugins")]

    async def list_plugin_install_operations(self) -> list[PluginInstallOperation]:
        """List all tracked plugin-install operations."""
        result = await self.query(QUERY_PLUGIN_INSTALL_OPERATIONS)
        return [PluginInstallOperation.model_validate(o) for o in _require_list(result, "pluginInstallOperations")]

    async def get_plugin_install_operation(self, operation_id: str) -> PluginInstallOperation:
        """Get a single plugin-install operation by ID.

        Raises:
            UnraidNotFoundError: when no operation matches ``operation_id``.
        """
        result = await self.query(QUERY_PLUGIN_INSTALL_OPERATION, variables={"operationId": operation_id})
        operation = result.get("pluginInstallOperation")
        if operation is None:
            raise UnraidNotFoundError(f"Plugin install operation '{operation_id}' not found")
        if not isinstance(operation, dict):
            raise UnraidError(f"Expected dict for 'pluginInstallOperation', got {type(operation).__name__}")
        return PluginInstallOperation.model_validate(operation)

    # ── Read methods: logs ──────────────────────────────────────────────

    async def list_log_files(self) -> list[LogFile]:
        """List available log files (name, path, size, mtime)."""
        result = await self.query(QUERY_LOG_FILES)
        return [LogFile.model_validate(f) for f in _require_list(result, "logFiles")]

    async def read_log_file(
        self,
        path: str,
        lines: int | None = None,
        start_line: int | None = None,
    ) -> LogFileContent:
        """Read (a slice of) a log file.

        Args:
            path: Absolute path to the log file.
            lines: Optional number of lines to return (paging window).
            start_line: Optional 1-indexed starting line for the window.
        """
        result = await self.query(
            QUERY_LOG_FILE,
            variables={"path": path, "lines": lines, "startLine": start_line},
        )
        return LogFileContent.model_validate(_require_dict(result, "logFile"))

    # ── Read methods: OIDC / SSO ────────────────────────────────────────

    async def get_sso_status(self) -> bool:
        """Return whether single sign-on (SSO) is enabled.

        Raises:
            UnraidError: when ``isSSOEnabled`` (a non-null schema field) is
                absent or not a boolean, signalling schema drift rather than a
                genuine ``False``.
        """
        result = await self.query(QUERY_SSO_STATUS)
        enabled = result.get("isSSOEnabled")
        if not isinstance(enabled, bool):
            raise UnraidError(
                f"Expected bool for 'isSSOEnabled', got {type(enabled).__name__}; run `unraid-mcp --check-schema`"
            )
        return enabled

    async def list_public_oidc_providers(self) -> list[PublicOidcProvider]:
        """List public OIDC providers (secret-free login-button projection)."""
        result = await self.query(QUERY_PUBLIC_OIDC_PROVIDERS)
        return [PublicOidcProvider.model_validate(p) for p in _require_list(result, "publicOidcProviders")]

    # ── Read methods: network / cloud / services / settings ─────────────

    async def get_network(self) -> Network:
        """Get the server's network access URLs."""
        result = await self.query(QUERY_NETWORK)
        return Network.model_validate(_require_dict(result, "network"))

    async def get_cloud(self) -> Cloud:
        """Get Unraid Connect cloud health (secret-free)."""
        result = await self.query(QUERY_CLOUD)
        return Cloud.model_validate(_require_dict(result, "cloud"))

    async def list_services(self) -> list[Service]:
        """List background services and their status."""
        result = await self.query(QUERY_SERVICES)
        return [Service.model_validate(s) for s in _require_list(result, "services")]

    async def get_display_settings(self) -> DisplaySettings:
        """Get UI display settings (case image ``base64`` omitted)."""
        result = await self.query(QUERY_DISPLAY)
        return DisplaySettings.model_validate(_require_dict(result, "display"))

    async def get_api_settings(self) -> ApiSettings:
        """Get the ``settings.api`` configuration branch."""
        result = await self.query(QUERY_API_SETTINGS)
        return ApiSettings.model_validate(_require_dict(result, "settings"))

    async def get_system_time(self) -> SystemTime:
        """Get the current server time configuration."""
        result = await self.query(QUERY_SYSTEM_TIME)
        return SystemTime.model_validate(_require_dict(result, "systemTime"))

    async def list_timezone_options(self) -> list[TimeZoneOption]:
        """List available IANA timezone options."""
        result = await self.query(QUERY_TIMEZONE_OPTIONS)
        return [TimeZoneOption.model_validate(t) for t in _require_list(result, "timeZoneOptions")]

    async def get_vars(self) -> Vars:
        """Get a curated, secret-free subset of Unraid system variables."""
        result = await self.query(QUERY_VARS)
        return Vars.model_validate(_require_dict(result, "vars"))

    # ── Read methods: disks (assignable) ────────────────────────────────

    async def list_assignable_disks(self) -> list[Disk]:
        """List disks eligible for assignment to the array."""
        result = await self.query(QUERY_ASSIGNABLE_DISKS)
        return [Disk.model_validate(d) for d in _require_list(result, "assignableDisks")]

    # ── Read methods: rclone ────────────────────────────────────────────

    async def get_rclone_config(self) -> RCloneConfig:
        """Get rclone backup configuration (credential JSON redacted)."""
        result = await self.query(QUERY_RCLONE_CONFIG)
        return RCloneConfig.model_validate(_require_dict(result, "rclone"))

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
        """Restart a Docker container by stopping then starting it.

        ``docker.restart`` was removed from the live schema in #59, so the
        client implements restart as a stop → start sequence on the
        caller's behalf. The returned payload merges both mutation
        responses under ``stop`` and ``start`` keys so callers still see
        the underlying GraphQL data when they need it.

        **Partial-failure note:** if the stop succeeds but the start
        fails, the container is left stopped — the raised
        :class:`UnraidError` mentions that the stop already completed so
        operators know which way to roll forward (call
        ``unraid_start_container`` to bring it back up). If the stop
        itself fails there is no partial state to report and the
        underlying exception propagates unchanged.

        Returns:
            ``{"stop": <stop response>, "start": <start response>}`` on
            success.
        """
        stop_result = await self.stop_container(container_id)
        try:
            start_result = await self.start_container(container_id)
        except UnraidError as exc:
            raise UnraidError(
                f"Container '{container_id}' was stopped successfully but "
                f"restart failed during start: {exc}. The container is "
                f"currently stopped; call unraid_start_container to recover.",
            ) from exc
        return {"stop": stop_result, "start": start_result}

    async def pause_container(self, container_id: str) -> dict[str, Any]:
        """Pause a Docker container by ID."""
        return await self.mutate(MUTATION_PAUSE_CONTAINER, variables={"id": container_id})

    async def unpause_container(self, container_id: str) -> dict[str, Any]:
        """Unpause a Docker container by ID."""
        return await self.mutate(MUTATION_UNPAUSE_CONTAINER, variables={"id": container_id})

    # ── Write methods: VMs ──────────────────────────────────────────────

    async def _vm_mutate(self, mutation: str, action: str, vm_id: str) -> dict[str, Any]:
        """Run a VM lifecycle mutation and normalize the ``Boolean!`` payload.

        Every VM mutation now returns ``Boolean!`` (#60), so the client
        flattens the response to ``{"ok": bool, "id": vm_id}`` — there's
        no domain object to return and callers still need to know which
        VM they acted on.

        Raises ``UnraidError`` when the payload is missing the expected
        ``vm.<action>`` field or returns a non-bool (#181): coercing such
        cases to ``ok=False`` would mask schema drift as a routine refusal.
        """
        result = await self.mutate(mutation, variables={"id": vm_id})
        vm_block = result.get("vm") if isinstance(result, dict) else None
        if not isinstance(vm_block, dict) or action not in vm_block:
            raise UnraidError(
                f"VM mutation '{action}' for {vm_id!r} returned unexpected payload "
                f"(missing vm.{action}): {result!r}. Schema may have changed; run "
                "`uv run unraid-mcp --check-schema`.",
            )
        ok = vm_block[action]
        if not isinstance(ok, bool):
            raise UnraidError(
                f"VM mutation '{action}' for {vm_id!r} returned non-bool result {ok!r}; expected Boolean!.",
            )
        return {"ok": ok, "id": vm_id}

    async def start_vm(self, vm_id: str) -> dict[str, Any]:
        """Start a VM by UUID."""
        return await self._vm_mutate(MUTATION_START_VM, "start", vm_id)

    async def stop_vm(self, vm_id: str) -> dict[str, Any]:
        """Gracefully stop a VM by UUID."""
        return await self._vm_mutate(MUTATION_STOP_VM, "stop", vm_id)

    async def pause_vm(self, vm_id: str) -> dict[str, Any]:
        """Pause a running VM by UUID."""
        return await self._vm_mutate(MUTATION_PAUSE_VM, "pause", vm_id)

    async def resume_vm(self, vm_id: str) -> dict[str, Any]:
        """Resume a paused VM by UUID."""
        return await self._vm_mutate(MUTATION_RESUME_VM, "resume", vm_id)

    async def reboot_vm(self, vm_id: str) -> dict[str, Any]:
        """Reboot a VM by UUID."""
        return await self._vm_mutate(MUTATION_REBOOT_VM, "reboot", vm_id)

    async def force_stop_vm(self, vm_id: str) -> dict[str, Any]:
        """Force-stop a VM by UUID (equivalent to pulling the plug)."""
        return await self._vm_mutate(MUTATION_FORCE_STOP_VM, "forceStop", vm_id)

    # ── Write methods: notifications ────────────────────────────────────

    async def archive_notification(self, notification_id: str) -> dict[str, Any]:
        """Archive a notification by ID."""
        return await self.mutate(MUTATION_ARCHIVE_NOTIFICATION, variables={"id": notification_id})

    async def delete_notification(
        self,
        notification_id: str,
        notification_type: NotificationType = "UNREAD",
    ) -> dict[str, Any]:
        """Delete a notification by ID.

        Args:
            notification_id: Notification ID (``PrefixedID``).
            notification_type: Which bin holds the entry — ``UNREAD``
                (default) or ``ARCHIVE``. Required by the live schema so
                the server can decrement the correct counter (#61).
        """
        return await self.mutate(
            MUTATION_DELETE_NOTIFICATION,
            variables={"id": notification_id, "type": notification_type},
        )

    async def archive_all_notifications(self, importance: NotificationImportance | None = None) -> dict[str, Any]:
        """Archive all unread notifications (optionally filtered by importance).

        Schema migration #176: ``archiveAll(importance: ...)`` was
        removed in Unraid API 4.32+ in favour of
        ``archiveNotifications(ids: [PrefixedID!]!)``. Importance-filter
        semantics are preserved client-side — list unread notifications,
        filter by importance if requested, then bulk-archive by ID.

        Args:
            importance: Optional ``NotificationImportance`` filter —
                limits the bulk archive to entries at that importance
                (``INFO`` / ``WARNING`` / ``ALERT``). Omit to archive
                every active notification.

        Returns:
            ``NotificationOverview`` payload after the bulk archive, or
            ``{"unread": None, "archive": None}`` when nothing matched.
        """
        notifs = await self.list_notifications(notification_type="UNREAD", limit=1000, offset=0)
        if importance is not None:
            notifs = [n for n in notifs if n.importance == importance]
        ids = [n.id for n in notifs if n.id is not None]
        if not ids:
            return {"unread": None, "archive": None}
        return await self.mutate(MUTATION_ARCHIVE_NOTIFICATIONS, variables={"ids": ids})

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
