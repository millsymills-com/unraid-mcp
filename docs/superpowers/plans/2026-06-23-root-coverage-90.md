# Implementation Plan — Unraid MCP Root-Field Coverage to ≥90%

## 1. Executive summary

**Today:** 21/118 roots covered by real tools (17.8%) — Query 14/57, Mutation 7/45, Subscription 0/16. All 118 are *handled* by the contract (covered or in `INTENTIONALLY_UNCOVERED`), so CI passes today; the gap is in *real tool coverage*, not contract compliance.

**The honest arithmetic finding (load-bearing — read before anything else):** the "≥90% (≥106/118)" target **cannot be met by adding real tools.** Taking *every* analyst-recommended add-tool plus the borderline `updateApiSettings` lifts covered-by-tool to only **~48% (57/118)**. The remaining ~52% of roots are genuinely declinable — secrets (`apiKey.key`, `OidcProvider.clientSecret`, `Server.apikey`), dangerous writes (`updateSettings`, `updateSshSettings`, plugin install, internal-boot-pool), UI bookkeeping (Docker organizer), and redundant-with-Query subscriptions.

**So ≥90% is reached the only way it can be: as ≥90% *resolved roots*** — every root either has a real tool *or* a precise, signed-off `INTENTIONALLY_UNCOVERED` rationale. The contract test (`test_no_unaccounted_root_fields`) already enforces 100% *resolution*; this plan's job is to (a) convert ~36 declined-but-valuable roots into real tools, and (b) re-justify the rest with sharper, per-field rationales (especially the 16 subscriptions, currently lumped under one stale "transport is request/response only" reason).

**Roots to newly cover with tools (Phase 1–3, excluding leaf-only work):**
- Query: **+22** → 36/57
- Mutation: **+13** root-moving (6 flat-notification roots + `rclone` namespace + 6 flat config/remote-access roots) → 20/45
- Subscription: **+0** in Phase 1 (all 16 served by Query snapshots → stay declined); **+3** only if the optional WebSocket Phase 4 ships.

**Net covered-by-tool: 21 → 56 (47.5%) after Phase 1–3; → 60 (50.8%) if optional WS Phase 4 lands.** Resolved roots: **118/118 (100%)** throughout, with the *declined* set shrinking from 97 to ~62 and every remaining decline carrying an agent-legible reason.

**Headline risk:** the subscription transport. The architect's decision (poll-as-snapshot for 13/16, hand-rolled `graphql-transport-ws` WebSocket for only 3) is correct and de-risks v1 by shipping **zero** new transport. The WebSocket path is the single place a new dependency, a second transport, close-code/auth divergence, and unbounded-stream hazards enter — it is correctly deferred behind a default-off flag and is **not on the critical path to the coverage target.**

> **Note to maintainer on the metric:** if "≥90%" is meant literally as *covered-by-tool*, it is unreachable without exposing secrets/dangerous writes and is the wrong goal. This plan treats ≥90% as *resolved roots* (the number the ratchet actually enforces) and maximizes *real* coverage underneath it. Confirm this interpretation (Decision D0 below).

---

## 2. Coverage math table

"Touched" = invoked by a `QUERY_*`/`MUTATION_*` (or, Phase 4 only, `SUBSCRIPTION_*`) constant. "Declined" = in `INTENTIONALLY_UNCOVERED`. Every root is one or the other (contract invariant). Today's covered baseline: Query 14, Mutation 7, Sub 0.

| Root type | Total | Covered today | + add-tool (this plan) | Resulting covered | Declined (resolved) | Covered % | Resolved % |
|---|--:|--:|--:|--:|--:|--:|--:|
| **Query** | 57 | 14 | **+22** | **36** | 21 | 63.2% | 100% |
| **Mutation** | 45 | 7 | **+13** | **20** | 25 | 44.4% | 100% |
| **Subscription** | 16 | 0 | **+0** (Phase 1–3) | **0** | 16 | 0% | 100% |
| **All roots (Phase 1–3)** | **118** | **21** | **+35** | **56** | **62** | **47.5%** | **100%** ✅ |
| *+ `updateApiSettings` (D2)* | 118 | 21 | +36 | 57 | 61 | 48.3% | 100% |
| *+ optional WS subs (Phase 4)* | 118 | 21 | +39 | 60 | 58 | 50.8% | 100% |

**The "All roots" resolved row is 100% ≥ 90% ✅** — the ratchet is satisfied because every root is accounted for. The covered-by-tool column is the real deliverable and it roughly **doubles** (17.8% → 47.5%).

### Mutation +13 breakdown (only roots that move the needle)
| Root | How it's touched |
|---|---|
| `createNotification`, `notifyIfUnique`, `unreadNotification`, `unarchiveNotifications`, `unarchiveAll`, `deleteArchivedNotifications` | 6 **flat** Mutation roots (not under a namespace — each is its own root) |
| `rclone` | namespace root, touched via `rclone { createRCloneRemote / deleteRCloneRemote }` |
| `updateTemperatureConfig`, `updateServerIdentity`, `updateSystemTime` | flat config writes |
| `initiateFlashBackup`, `setupRemoteAccess`, `enableDynamicRemoteAccess` | flat remote-access/backup writes (gated) |

### Explicitly NOT counted toward 90% (leaf-only — zero root impact, verified)
`array.addDiskToArray/removeDiskFromArray/mountArrayDisk/unmountArrayDisk/clearArrayDiskStatistics`, `vm.reset`, `docker.removeContainer/updateContainer/updateContainers/updateAllContainers/updateAutostartConfiguration` — all sit under `array`/`vm`/`docker` Mutation roots **already touched** by existing tools. Building these (Phase 5) improves *leaf* coverage (`SCHEMA_EXPECTATIONS` / `docs/coverage-matrix.md`) and agent value, but **does not change the root ratchet.** They are worth doing for their own sake, sequenced last.

---

## 3. Phased delivery plan

Each phase is one shippable PR. Every PR must, for each promoted root: (1) add `QUERY_*`/`MUTATION_*` constant + typed client method in `clients/unraid.py`; (2) add `SCHEMA_EXPECTATIONS` leaf entry; (3) add model(s) in `models/` (`extra="allow"`); (4) register the tool; (5) **remove** the field from `INTENTIONALLY_UNCOVERED` (else `test_registry_has_no_stale_entries` fails "now covered"); (6) update `docs/coverage-matrix.md`. Run `uv run pytest tests/contract -q` + `uv run ty check` + `uv run ruff check` before commit.

### Phase 1 — Pure read coverage, zero new transport/deps/flags (LOW risk)
The fastest, safest needle-mover: **+18 Query roots**, all request/response, all reusing `base.py`.

- **New `tools/metrics.py`** — `unraid_get_metrics` (Query `metrics`; fold CPU+memory+temperature into one tool). Models: `Metrics`, `CpuUtilization`, `MemoryUtilization`, `TemperatureMetrics`, `TemperatureSensor`, `TemperatureSummary`. **Select `cpu.percentTotal`+`cpu.cpus`(load only), all memory scalars, `temperature.summary`+`temperature.sensors` but OMIT `sensors[].history`** (unbounded; belongs to the stream). BigInt memory → `str`.
- **New `tools/ups.py`** — `unraid_list_ups_devices` (`upsDevices`), `unraid_get_ups_device` (`upsDeviceById`, nullable), `unraid_get_ups_configuration` (`upsConfiguration`). Models `models/ups.py`: `UPSDevice`/`UPSBattery`/`UPSPower`/`UPSConfiguration`.
- **New `tools/plugins.py`** — `unraid_list_plugins` (`plugins`), `unraid_list_installed_plugins` (`installedUnraidPlugins` → `list[str]`), `unraid_list_plugin_install_operations` (`pluginInstallOperations`), `unraid_get_plugin_install_operation` (`pluginInstallOperation`, nullable). Models: `Plugin`, `PluginInstallOperation`.
- **New `tools/logs.py`** — `unraid_list_log_files` (`logFiles`), `unraid_read_log_file` (`logFile(path, lines, startLine)` — explicit optional `lines`/`start_line` params for paging). Models `models/logs.py`: `LogFile`, `LogFileContent`. (The *Subscription* `logFile(path)` stays declined — the Query is strictly richer.)
- **New `tools/oidc.py`** — `unraid_get_sso_status` (`isSSOEnabled` → bool), `unraid_list_public_oidc_providers` (`publicOidcProviders`). Model `models/oidc.py`: `PublicOidcProvider` (secret-free projection — **never** add `OidcProvider`).
- **Extend `tools/system.py`** — `unraid_get_network` (`network`), `unraid_get_cloud` (`cloud`; select health fields, **avoid echoing any token-like subfield of `ApiKeyResponse`**), `unraid_list_services` (`services`), `unraid_get_display_settings` (`display`; default-omit `case.base64`), `unraid_get_api_settings` (`settings`, **`.api` branch only** — skip `.unified`/`.sso` JSON form blobs), `unraid_get_system_time` (`systemTime`), `unraid_list_timezone_options` (`timeZoneOptions`), `unraid_get_vars` (`vars` — **curated subset, MUST omit `csrfToken`** per PROTO-012). Extend `tools/disks.py` with `unraid_list_assignable_disks` (`assignableDisks`, reuse existing `Disk` model).
- **New `tools/rclone.py`** (read half) — `unraid_get_rclone_config` (`rclone`; select `remotes`+`drives`, skip `configForm`; **redact `parameters`/`config` JSON — may carry cloud creds, PROTO-012**). Model `models/rclone.py`.

**Registry edits:** remove the promoted names from Query groups "config, settings & display", "plugins", "UPS", "metrics & logs", "network & cloud", "identity & multi-server inventory", and `isSSOEnabled`/`publicOidcProviders` from "OIDC / SSO". Reword the OIDC group to keep `oidcProviders`/`oidcProvider`/`oidcConfiguration`/`validateOidcSession` declined with the sharpened secret-leak reason.
**Effort:** L (≈18 tools, ~8 model files) but mechanically uniform. New deps: none. New flags: none.

### Phase 2 — Notification-lifecycle writes + read overview (LOW risk, +6 Mutation roots, +0 Query)
Six **flat** Mutation roots that are gated but benign.

- **Extend `tools/notifications.py`** (all `{"write"}`, `readOnlyHint=False`, `require_readwrite`): `unraid_create_notification` (`createNotification`), `unraid_notify_if_unique` (`notifyIfUnique`, nullable return = suppressed dup), `unraid_mark_notification_unread` (`unreadNotification`), `unraid_unarchive_notifications` (`unarchiveNotifications`), `unraid_unarchive_all_notifications` (`unarchiveAll`), `unraid_delete_archived_notifications` (`deleteArchivedNotifications`, `destructiveHint=True`). Reuse `Notification`/`NotificationImportance`; `NotificationOverview` → raw dict.
- Optionally add a read `unraid_get_notifications_overview` if you also want the `notifications.overview` leaf (leaf-only, no root impact; nice-to-have).
- **Keep declined:** `archiveAll` (already shipped as `unraid_archive_all_notifications` — do NOT duplicate; leave in registry), `recalculateOverview` (internal housekeeping; keep declined, reason=internal).

**Registry edits:** remove the 6 promoted names from the "notification lifecycle" group; keep `archiveAll` + `recalculateOverview`. **Effort:** M. Deps/flags: none new (reuses write gate).

### Phase 3 — Config & rclone writes (MEDIUM risk, +7 Mutation roots: rclone namespace + 4 flat)
- **Extend `tools/rclone.py`** (write half): `unraid_create_rclone_remote` (`rclone.createRCloneRemote`), `unraid_delete_rclone_remote` (`rclone.deleteRCloneRemote`). The `MUTATION_*` constant **must wrap `rclone { createRCloneRemote(input:…) }`** — that selects `rclone` as the touched Mutation root (verified: same shape as existing `array { setState }`). Never log `parameters` JSON. This single namespace touch is worth +1 root.
- **Extend `tools/system.py`**: `unraid_update_temperature_config` (`updateTemperatureConfig`; typed `TemperatureConfigInput`), `unraid_update_server_identity` (`updateServerIdentity`; flat `name`/`comment`/`sysModel`), `unraid_update_system_time` (`updateSystemTime`; **`UpdateSystemTimeInput` has 4 fields — `timeZone`, `useNtp`, `ntpServers`, and `dateTime: String` (YYYY-MM-DD HH:mm:ss, used when NTP disabled)** — verified at snapshot L3532–3545; include all four as optional params, build the input omitting unset keys). Pairs with the Phase-1 `unraid_get_system_time` / `unraid_list_timezone_options` reads.
- **New `tools/flash.py` or extend `tools/rclone.py`**: `unraid_initiate_flash_backup` (`initiateFlashBackup`; returns `FlashBackupStatus{status, jobId}`; `remoteName` ties to `unraid_get_rclone_config`). Model `models/flash.py`.

All `{"write"}`, `readOnlyHint=False`, `require_readwrite`. **Registry edits:** remove these from "settings & system configuration mutations", "UPS configuration" (see Phase 5 for `configureUps`), "Connect / cloud / remote-access setup" (`initiateFlashBackup`), and `rclone` from "mutation namespaces not implemented". **Effort:** M–L. Deps/flags: none new.

### Phase 4 — Remote-access writes + (optional) WebSocket subscriptions (HIGH risk — gated, last)
**4a. Remote-access writes (+2 Mutation roots):** `unraid_setup_remote_access` (`setupRemoteAccess`; `WAN_ACCESS_TYPE`/`WAN_FORWARD_TYPE` enums, `port` required for STATIC), `unraid_enable_dynamic_remote_access` (`enableDynamicRemoteAccess`; `AccessUrlInput`). Both `{"write"}` + `require_readwrite`; docstrings **must** warn they alter external WAN exposure. Remove from "Connect / cloud / remote-access setup". *Subject to Decision D1.*

**4b. Optional WebSocket subscriptions (+3 Subscription roots) — default-off, behind a new flag, NOT required for the coverage target.** See §4. Only ship if a concrete consumer appears.

### Phase 5 — Leaf-coverage write gaps (no root impact, sequenced last)
`array.addDiskToArray/removeDiskFromArray/mountArrayDisk/unmountArrayDisk/clearArrayDiskStatistics`, `vm.reset`, `docker.removeContainer/updateContainer/updateContainers/updateAllContainers/updateAutostartConfiguration`, and `configureUps`. Each improves `SCHEMA_EXPECTATIONS` leaf coverage and agent value; none changes the root ratchet. All gated writes. `removeContainer`/disk-removal carry `destructiveHint=True`.

---

## 4. Subscription strategy

**Architect's transport decision (endorsed):** the Unraid endpoint is Apollo Server; subscriptions are **WebSocket-only** (`graphql-transport-ws` subprotocol, same `/graphql` URL, `x-api-key` in `connectionParams`). There is no SSE. Because **13 of 16 subscription payload types are already reachable through a Query root**, the right move is *poll-as-snapshot*: cover the information value with the Phase-1 request/response tools and **leave the subscription roots declined**, re-justified per field.

**How the 16 roots get registered to count (all stay in `INTENTIONALLY_UNCOVERED['Subscription']`, but the single stale group is split into precise rationales):**

| Subscription root | Disposition | Rationale group |
|---|---|---|
| `systemMetricsCpu`, `systemMetricsMemory`, `systemMetricsTemperature` | declined | "served by Query.metrics snapshot" |
| `logFile` | declined | "served by richer Query.logFile(path,lines,startLine)" |
| `upsUpdates` | declined | "served by Query.upsDevices/upsDeviceById" |
| `arraySubscription`, `parityHistorySubscription` | declined | "served by Query.array / Query.parityHistory" |
| `notificationsOverview`, `notificationsWarningsAndAlerts` | declined | "served by Query.notifications(+overview/importance filter)" |
| `displaySubscription`, `ownerSubscription`, `serversSubscription` | declined | "UI/identity config, low agent value (Query also declined)" |
| `systemMetricsCpuTelemetry` | declined | "per-package power telemetry, no Query equivalent, niche" |
| `dockerContainerStats`, `notificationAdded`, `pluginInstallUpdates` | declined in Phase 1; **only these 3 are WS candidates** | "push-only, no Query snapshot — see Phase 4b" |

This satisfies the ratchet **with zero new transport in Phase 1.** The registry must be re-grouped into disjoint sets (`test_registry_groups_are_disjoint`).

**Phase 4b WebSocket path (optional, the headline risk, gated):**
- **Flag:** new `config.unraid_enable_subscriptions: bool = False` (+ `unraid_subscription_max_events`, `unraid_subscription_window_seconds` bounds). **Do not overload the write gate** — telemetry is read-side; `pluginInstallUpdates` additionally gets `{"write"}`.
- **Dep:** `websockets>=15` only (pure-Python; hand-roll the ~5-message `graphql-transport-ws` handshake — do **not** pull `gql[websockets]`/Apollo clients).
- **Critical contract change:** widen the `_surface.py` regex from `(?:QUERY|MUTATION)_\w+` to `(?:QUERY|MUTATION|SUBSCRIPTION)_\w+` (verified: subscription *bodies* already parse via `OperationType.SUBSCRIPTION`, but the constant-scanning regex won't pick up `SUBSCRIPTION_*` names). Without this, WS tools won't register as covered and the ratchet still flags the 3 roots.
- **base.py:** add `subscribe_window(document, variables, *, max_events, timeout)` — sample-N-then-close (collect bounded window, always `Complete`+close in `finally`). Reuse `verify_ssl` (scheme-swap https→wss), extend the API-key redaction filter to the `websockets` logger, map close codes 4401/4403→`UnraidAuthError`.
- **Tools:** `unraid_sample_container_stats`, `unraid_wait_for_notification`, `unraid_poll_plugin_install` (write-tagged). Remove the 3 from the declined group; register only `if config.enable_subscriptions`.

---

## 5. Decisions needed from the maintainer

- **D0 — metric definition — RESOLVED (2026-06-23): maximize real coverage.** Maintainer confirmed the goal is to roughly double covered-by-tool roots (17.8% → 47.5% via P1–P3), not chase a literal 90% covered-by-tool figure (unreachable without exposing secrets/dangerous writes, ~48% ceiling). Resolved roots stay at 100% (ratchet already green). Build P1–P3; P4/P5 optional.
- **D1 — remote-access writes (Phase 4a).** Add `setupRemoteAccess` + `enableDynamicRemoteAccess` as gated write tools (they change external WAN exposure / port forwarding), or keep declined? Defensible either way; both are already resolved.
- **D2 — `updateApiSettings`.** Configures Unraid Connect WAN exposure + port forwarding (HIGH risk, but enum-constrained typed input). Add as a gated write, or leave declined? (+1 Mutation root if added.) Recommend **declined** unless remote-access management is explicitly wanted.
- **D3 — WebSocket subscriptions (Phase 4b).** Ship the optional `websockets` path now, or defer until a concrete consumer (`dockerContainerStats` etc.) appears? Recommend **defer** — it's the only new dependency/transport and adds just 3 roots of marginal value over polling.
- **D4 — plugin install/SSH/JSON-settings writes.** Confirm `unraidPlugins`/`addPlugin`/`removePlugin` (RCE-class, auto-restart the API), `updateSshSettings` (remote-shell exposure), `updateSettings` (untyped `JSON!`, violates PROTO-002, unbounded blast radius), `onboarding.createInternalBootPool` (can flash BIOS/reboot), and the API-key/OIDC-secret reads all **stay declined**. These are the genuine "no safe tool shape" set; sign off to keep them out.

---

## 6. Honest risks & non-goals

**What ≥90% (resolved) buys:** 100% of roots are accounted for and CI-enforced; real tool coverage roughly doubles (21→56), covering the operationally valuable read surface (metrics, UPS, plugins, logs, network/cloud/services, system time, vars) and the benign write surface (notifications, rclone remotes, temp config, server identity, system time). Every uncovered root now carries an agent-legible reason instead of one stale bucket.

**What it does NOT buy:** it is **not** ~90% of the *functional* API behind tools. ~52% of roots remain tool-less by design. Subscriptions deliver **zero** live-streaming capability in Phase 1–3 (snapshot reuse only); true push (`dockerContainerStats`, `notificationAdded`) requires the deferred WS path.

**Risks / gotchas (verified against schema + contract code):**
- **Registry rot, both directions.** Promoting a field without deleting its `INTENTIONALLY_UNCOVERED` entry fails `test_registry_has_no_stale_entries` ("now covered"); the subscription re-grouping must keep groups disjoint (`test_registry_groups_are_disjoint`). Every PR touches the registry + `docs/coverage-matrix.md` in lockstep.
- **Subscription-constant blind spot.** `_surface.py`'s regex is `(?:QUERY|MUTATION)_\w+` — confirmed it will silently miss `SUBSCRIPTION_*` constants. Phase 4b must widen it or WS coverage won't count.
- **Secret leakage is the recurring hazard** (PROTO-012): `vars.csrfToken`, `rclone` `parameters`/`config`, `cloud.apiKey` subfields — each promoted tool must omit/redact. Confirmed `ApiKey.key: String!` is plaintext (snapshot L703–711) and `OidcProvider.clientSecret` exists — these stay declined.
- **Unbounded payloads:** `metrics.temperature.sensors[].history` and any WS stream must be bounded; the WS `finally`-close discipline is mandatory or a misbehaving server hangs the agent turn.

**Could not fully resolve from the schema (verify at implementation time):**
- `updateApiSettings` exact input/return (`ConnectSettingsInput`/`ConnectSettingsValues`) — analyst-reported, not re-verified; verify before D2.
- `URL_TYPE` enum members (needed for `AccessUrlInput` in Phase 4a) — analyst flagged "confirm members".
- The `rclone` read response shape beyond `remotes`/`drives`/`configForm` — confirm `RCloneRemote.config` field name.

**One corrected analyst datum:** `UpdateSystemTimeInput` has a **4th field, `dateTime: String`** (manual time when NTP is off), which two analysts truncated — confirmed at snapshot L3532–3545. Include it in `unraid_update_system_time`.

**Files touched across all phases:** `src/unraid_mcp/clients/unraid.py` (constants + methods + `SCHEMA_EXPECTATIONS`), new `tools/{metrics,ups,plugins,logs,oidc,rclone,flash}.py` + edits to `tools/{system,disks,notifications}.py`, new `models/{ups,plugins,logs,oidc,rclone,flash,metrics,network,settings,system_time,vars}.py`, `tests/contract/test_root_coverage.py` (registry), `docs/coverage-matrix.md`, and (Phase 4b only) `config.py`, `clients/base.py`, `server.py`, `tests/contract/_surface.py`.
