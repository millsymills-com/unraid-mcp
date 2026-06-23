# Tool ↔ Schema Coverage Matrix

Precise mapping of `unraid-mcp` tools to the Unraid GraphQL API surface.

- **Schema source:** `tests/contract/snapshot.graphql` (the pinned introspection
  snapshot the drift test asserts against).
- **Tools source:** `src/unraid_mcp/tools/` (36 domain tools: 16 read, 20 write).
- **Legend:** ✓ covered · ◐ partial (namespace reached, some leaves missing) ·
  ✗ not implemented.
- **Enforced by** `tests/contract/test_root_coverage.py`: every **root** field
  must be invoked by a `QUERY_*`/`MUTATION_*` client operation constant or listed
  in that test's `INTENTIONALLY_UNCOVERED` registry. A new schema root field with
  neither fails CI. The ratchet guards root fields only — leaf-op coverage in the
  tables below (e.g. `docker` 4/9) is descriptive; the leaf contract lives in
  `SCHEMA_EXPECTATIONS` in `clients/unraid.py`, checked by the drift tests. Keep
  this doc and that registry in step.

## Headline numbers

| Root type | Schema fields | Touched | Coverage |
|-----------|--------------:|--------:|---------:|
| `Query` | 57 | 14 | **24.6%** |
| `Mutation` (root fields) | 45 | 7 | **15.6%** |
| `Subscription` | 16 | 0 | **0%** |
| **All roots** | **118** | **21** | **17.8%** |

Operation-level (expanding the 4 mutation namespaces we reach into):

| Surface | Operations | Covered | Coverage |
|---------|-----------:|--------:|---------:|
| Mutation leaf ops (`array`/`docker`/`vm`/`parityCheck` + flat) | 37 | 18 | **48.6%** |

The split is deliberate: read coverage is broad-but-shallow over operational
state; write coverage is deep on lifecycle namespaces (array, parity, Docker,
VM, notifications) and absent everywhere else (config, auth, plugins, UPS, cloud).

## Query (14 / 57)

| Query field | Tool | Status |
|-------------|------|:------:|
| `info` | `unraid_get_info` | ✓ |
| `array` | `unraid_get_array` | ✓ |
| `parityHistory` | `unraid_get_parity_history` | ✓ |
| `disks` | `unraid_list_disks` | ✓ |
| `disk` | `unraid_get_disk` | ✓ |
| `docker` | `unraid_list_containers`, `unraid_get_container`, `unraid_list_docker_networks` | ✓ |
| `vms` | `unraid_list_vms` | ✓ |
| `shares` | `unraid_list_shares`, `unraid_get_share` | ✓ |
| `me` | `unraid_get_me` | ✓ |
| `notifications` | `unraid_list_notifications` | ✓ |
| `flash` | `unraid_get_flash` | ✓ |
| `registration` | `unraid_get_registration` | ✓ |
| `connect` | `unraid_get_connect` | ✓ |
| `remoteAccess` | `unraid_get_connect` (combined query) | ✓ |
| `apiKeys` / `apiKey` / `apiKeyPossibleRoles` / `apiKeyPossiblePermissions` / `getPermissionsForRoles` / `previewEffectivePermissions` / `getAvailableAuthActions` / `getApiKeyCreationFormSchema` | — | ✗ |
| `config` / `settings` / `customization` / `display` / `publicTheme` | — | ✗ |
| `isSSOEnabled` / `publicOidcProviders` / `oidcProviders` / `oidcProvider` / `oidcConfiguration` / `validateOidcSession` | — | ✗ |
| `metrics` | — | ✗ |
| `upsDevices` / `upsDeviceById` / `upsConfiguration` | — | ✗ |
| `plugins` / `installedUnraidPlugins` / `pluginInstallOperation` / `pluginInstallOperations` | — | ✗ |
| `rclone` | — | ✗ |
| `logFiles` / `logFile` | — | ✗ |
| `network` / `cloud` | — | ✗ |
| `server` / `servers` / `services` | — | ✗ |
| `systemTime` / `timeZoneOptions` / `vars` | — | ✗ |
| `online` / `owner` / `internalBootContext` / `isFreshInstall` / `assignableDisks` | — | ✗ |

## Mutation

### Flat notification mutations (3 / 11)

| Mutation field | Tool | Status |
|----------------|------|:------:|
| `archiveNotification` | `unraid_archive_notification` | ✓ |
| `archiveNotifications` | `unraid_archive_all_notifications` | ✓ |
| `deleteNotification` | `unraid_delete_notification` | ✓ |
| `createNotification` / `notifyIfUnique` / `unreadNotification` / `unarchiveNotifications` / `unarchiveAll` / `archiveAll` / `deleteArchivedNotifications` / `recalculateOverview` | — | ✗ |

### `array: ArrayMutations` (1 / 6) — ◐

| Field | Tool | Status |
|-------|------|:------:|
| `setState` | `unraid_start_array` (START), `unraid_stop_array` (STOP) | ✓ |
| `addDiskToArray` / `removeDiskFromArray` / `mountArrayDisk` / `unmountArrayDisk` / `clearArrayDiskStatistics` | — | ✗ |

### `parityCheck: ParityCheckMutations` (4 / 4) — ✓ full

| Field | Tool | Status |
|-------|------|:------:|
| `start` | `unraid_start_parity_check` | ✓ |
| `pause` | `unraid_pause_parity_check` | ✓ |
| `resume` | `unraid_resume_parity_check` | ✓ |
| `cancel` | `unraid_cancel_parity_check` | ✓ |

### `docker: DockerMutations` (4 / 9) — ◐

| Field | Tool | Status |
|-------|------|:------:|
| `start` | `unraid_start_container` | ✓ |
| `stop` | `unraid_stop_container` | ✓ |
| `pause` | `unraid_pause_container` | ✓ |
| `unpause` | `unraid_unpause_container` | ✓ |
| `removeContainer` / `updateAutostartConfiguration` / `updateContainer` / `updateContainers` / `updateAllContainers` | — | ✗ |

> `unraid_restart_container` has no matching schema field — it is a client-side
> `stop` → `start` sequence (the upstream `docker.restart` mutation was removed
> in Unraid API 4.32+).

### `vm: VmMutations` (6 / 7) — ◐

| Field | Tool | Status |
|-------|------|:------:|
| `start` | `unraid_start_vm` | ✓ |
| `stop` | `unraid_stop_vm` | ✓ |
| `pause` | `unraid_pause_vm` | ✓ |
| `resume` | `unraid_resume_vm` | ✓ |
| `reboot` | `unraid_reboot_vm` | ✓ |
| `forceStop` | `unraid_force_stop_vm` | ✓ |
| `reset` | — | ✗ |

### Untouched mutation namespaces & config mutations (0 covered)

`apiKey`, `customization`, `rclone`, `onboarding`, `unraidPlugins` (namespaces);
`updateServerIdentity`, `updateSshSettings`, `updateSettings`,
`updateApiSettings`, `updateSystemTime`, `updateTemperatureConfig`,
`configureUps`, `addPlugin`, `removePlugin`, `initiateFlashBackup`,
`connectSignIn`, `connectSignOut`, `setupRemoteAccess`,
`enableDynamicRemoteAccess`, and the 9 `*DockerFolder*` / `*DockerEntries*` /
`*DockerView*` / `*DockerTemplate*` / `refreshDockerDigests` organizer
mutations — all ✗.

## Subscription (0 / 16)

No subscriptions are implemented. The transport is request/response only.
Uncovered: `displaySubscription`, `notificationAdded`, `notificationsOverview`,
`notificationsWarningsAndAlerts`, `ownerSubscription`, `serversSubscription`,
`parityHistorySubscription`, `arraySubscription`, `dockerContainerStats`,
`logFile`, `systemMetricsCpu`, `systemMetricsCpuTelemetry`,
`systemMetricsMemory`, `systemMetricsTemperature`, `upsUpdates`,
`pluginInstallUpdates`.
