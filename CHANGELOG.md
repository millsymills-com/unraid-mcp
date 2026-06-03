# Changelog

All notable changes to `unraid-mcp` are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Layered test suite: `tests/property/` (Hypothesis fuzzing on parsers,
  config, and error mapping), `tests/e2e/` (MCP stdio transport tests
  with mocked GraphQL endpoint), `tests/contract/` (GraphQL schema
  snapshot pinning + drift detection), and `tests/live_write/` (gated
  mutating tests on `mcptest_*` assets).
- Per-tool live-coverage manifest in `tests/integration/_coverage.py`
  with meta-tests that enforce every registered MCP tool has a live
  test.
- Three-layer write gating for live mutating tests: `pytest -m
  live_write` marker + `UNRAID_ALLOW_LIVE_WRITES=1` env flag +
  `mcptest_*` asset name invariant. Pre-flight banner with 3-second
  abort window.
- Branch coverage gate raised from 80% to 90%.

### Changed
- `unraid_get_container` and `unraid_get_disk` now issue direct
  single-entity GraphQL queries (`Docker.container(id: PrefixedID!)` and
  `Query.disk(id: PrefixedID!)`) instead of fetching the full roster and
  scanning client-side. On Unraid API 4.32+ this is O(1) per lookup; on
  older schemas without the singular fields the client catches
  `GRAPHQL_VALIDATION_FAILED` and falls back to list-then-filter so the
  tool surface stays identical. The Unraid schema does not expose a
  singular `share` query, so `unraid_get_share` keeps the list-and-scan
  path, encapsulated on the client now for symmetry. New
  `UnraidClient.get_container`, `get_disk`, `get_share` methods own the
  lookup logic; the corresponding `list_*` methods are unchanged (#36).

### Fixed
- Corrected the GitHub org in documented clone, install, and
  security-reporting URLs and in packaging metadata from
  `millsmillsymills` to `millsymills-com`, matching the actual remote
  (#203).

### Added
- `unraid_get_me` read tool, backed by the new `Query.me` selection set
  (`{ id name description roles }`). Returns the single `UserAccount`
  matching the API key in use, the only account coverage left after
  Unraid 7.2+ removed `Query.users` from the GraphQL API (#57).
- README subsection documenting the nightly `--check-schema` CI probe,
  the Actions secrets required to enable it on a fork (`UNRAID_HOST`
  and `UNRAID_API_KEY`, plus optional `UNRAID_PORT` /
  `UNRAID_USE_HTTPS` / `UNRAID_VERIFY_SSL` overrides), and how to
  disable the workflow if a fork doesn't operate a test server (#153).

### Removed
- **Breaking:** `unraid_list_users`, `unraid_create_user`, and
  `unraid_delete_user` tools. Unraid 7.2+ removed `Query.users`,
  `addUser`, and `deleteUser` from the GraphQL API, so the MCP
  server can no longer expose them. Use `unraid_get_me` (returns
  the authenticated account) for the remaining read coverage; manage
  Unraid users via the WebGUI or `unraid-api` CLI on the server (#57).
- **Breaking:** `UNRAID_ALLOW_USER_MUTATIONS` and `UNRAID_NEW_USER_*`
  environment variables. The secondary `user-mutation` tag gate, the
  `require_user_mutation` helper, and the `password_env_var` argument
  resolution are gone with the tools they protected (#57).

### Fixed
- Aligned the Docker, VM, notification, array, and parity write
  mutations with the Unraid API 4.32+ schema. `SCHEMA_EXPECTATIONS`
  is updated in lockstep so `unraid-mcp --check-schema` keeps catching
  drift at boot.
  - Docker write mutations (`unraid_start_container`,
    `unraid_stop_container`, `unraid_pause_container`,
    `unraid_unpause_container`): `$id` retyped from `ID!` to
    `PrefixedID!`. `unraid_restart_container` is reimplemented as a
    client-side stop → start because `docker.restart` was removed
    from the schema; the tool now returns the merged
    `{"stop": ..., "start": ...}` payload (#59).
  - Array lifecycle mutations (`unraid_start_array`,
    `unraid_stop_array`): root-level `startArray` / `stopArray` were
    removed; replaced with `array.setState(input: {desiredState:
    START | STOP})` and the matching `SCHEMA_EXPECTATIONS["Mutation"]`
    / `ArrayMutations` entries.
  - Parity mutations (`unraid_start_parity_check`,
    `unraid_pause_parity_check`, `unraid_resume_parity_check`,
    `unraid_cancel_parity_check`): root-level mutations were removed;
    replaced with `parityCheck.{start,pause,resume,cancel}` (JSON-ish
    return, no selection set).
  - VM write mutations (all six): the mutations now return
    `Boolean!`, so the `{uuid name state}` selection sets are dropped
    and `$id` is retyped to `PrefixedID!`. Client methods normalise
    the response to `{"ok": bool, "id": vm_id}` since there's no
    domain object to surface (#60).
  - Notification write mutations: `$id` is `PrefixedID!`.
    `deleteNotification` gained a required `type: NotificationType!`
    argument so the server knows which bin's counter to decrement;
    `unraid_delete_notification` takes a new `notification_type`
    parameter (default `UNREAD`). `archiveAll` accepts an optional
    `importance: NotificationImportance` filter exposed on
    `unraid_archive_all_notifications` as the `importance` parameter.
    Return selections track the updated `NotificationOverview`
    (`unread { total info warning alert } archive { ... }`) instead
    of the removed `id` field (#61).
- Schema-probe workflow (`.github/workflows/schema-probe.yml`) now
  selects the oldest open `schema-drift` issue for dedup by adding
  `--search "sort:created-asc"` to the `gh issue list` call.
  `gh issue list` defaults to `sort:created-desc`, so the previous
  query returned the newest issue, contradicting the documented intent
  of reusing the issue with accumulated history (#159).
- Reverted `Disk.size` from `int | None` back to `str | None` to match
  `ArrayDisk.size` and `Share.size`. Unraid byte scalars serialize as
  JSON strings and non-numeric values (`"4 TB"`, `"-"`) would have
  failed validation under the `int` typing introduced in #154 (#158).
- Aligned six read queries with the Unraid API 4.32+ schema, verified
  against a live Unraid 7.x / API 4.32 server. `SCHEMA_EXPECTATIONS` is
  updated in lockstep so `unraid-mcp --check-schema` and the boot-time
  drift probe keep reporting accurately.
  - `unraid_get_info`: `info.memory` switches from aggregated totals to
    per-DIMM `layout` entries; `info.versions` splits into nested
    `core { unraid kernel api }` and `packages { openssl docker node npm
    nginx php git pm2 }` objects. `CpuInfo.stepping` accepts `int | str`
    since the live schema types it as `Int` (#51).
  - `unraid_get_connect`: `Connect.dynamicRemoteAccessType` became a
    nested `dynamicRemoteAccess { enabledType runningType error }`
    object, and the legacy `config { accessType forwardType port }`
    fields moved to the sibling top-level `remoteAccess` query. Both
    are fetched together and merged into one combined return shape
    (#53).
  - `unraid_list_disks` / `unraid_get_disk`: `Disk.temp` →
    `temperature`, `Disk.interface` → `interfaceType`, `rotational`
    removed (closest live equivalent is the inverse of `isSpinning`),
    `vendor` and `isSpinning` added (#54).
  - `unraid_list_containers` / `unraid_get_container`: top-level
    `Query.dockerContainers` removed in favor of `docker.containers`;
    `DockerContainer.networkMode` removed (#55).
  - `unraid_list_docker_networks`: same regrouping as #55,
    `Query.dockerNetworks` → `docker.networks`. `enableIPv6` added
    (#56).
  - `unraid_list_notifications`: `Notifications.list(filter:
    NotificationFilter)`: `type` is required, so the tool takes a
    `notification_type` parameter (`UNREAD` default, `ARCHIVE`
    opt-in) plus `limit` / `offset` pagination (#58).

### Changed
- Tightened the `notification_type` and `importance` parameters on
  `unraid_list_notifications`, `unraid_delete_notification`, and
  `unraid_archive_all_notifications` from bare `str` to
  `Literal["UNREAD", "ARCHIVE"]` and
  `Literal["INFO", "WARNING", "ALERT"]` aliases exported from
  `unraid_mcp.models.notifications`. FastMCP now renders these as
  JSON-Schema `enum` constraints so invalid values are rejected at
  the MCP boundary instead of being forwarded to the Unraid
  GraphQL API (#165).
- `UnraidClient.restart_container` (and the `unraid_restart_container`
  tool) now signals partial failure when the client-side stop → start
  sequence (#59) only completes the stop. If the stop succeeds but the
  subsequent start raises, the client now wraps the start error in an
  `UnraidError` that names the container, states the stop already
  completed, and points operators at `unraid_start_container` for
  roll-forward; the original exception is chained via `__cause__`. The
  tool docstring is updated to describe the
  `{"stop": ..., "start": ...}` return shape and the partial-failure
  semantics. Failures during the stop itself propagate unchanged
  because there is no partial state to report (#164).
- Schema-probe workflow (`.github/workflows/schema-probe.yml`) now
  publishes drift output to `$GITHUB_STEP_SUMMARY` on failure and
  auto-creates / updates a GitHub issue labelled `bug,schema-drift`
  with the drift report. De-duplicates by reusing the oldest open
  drift issue. Operators can opt out per run via the
  `suppress_issue` workflow_dispatch input. The job still exits red
  on drift so required-status-check semantics are preserved (#152).

### Changed
- Retry policy split by operation type in `BaseGraphQLClient._post`.
  Queries retry on `ConnectError`, `TimeoutException`, and the new
  `UnraidServerError` (HTTP 5xx). Mutations retry on `ConnectError`
  only; `TimeoutException` and 5xx no longer duplicate writes whose
  side effects may already have landed (e.g. `start_array`,
  `start_parity_check`, `create_user`, every container/VM lifecycle
  tool). Added `UnraidServerError(UnraidError)` for HTTP 5xx; mapped
  to a clear "server returned 5xx; often transient" ToolError (#63,
  #75).
- Centralised the per-tool error-handling boilerplate behind a new
  `unraid_tool` decorator in `tools/_helpers.py`. Every tool in
  `tools/{system,array,parity,disks,docker,vms,shares,users,notifications}.py`
  drops its `try: ... except Exception as e: handle_client_error(e)`
  wrapper and registers via `@unraid_tool(mcp, ...)`. The decorator
  **narrows the catch to `UnraidError`** so programming bugs
  (`KeyError`, `AttributeError`, `TypeError`) propagate to FastMCP with
  a full stacktrace instead of being disguised as "Unexpected error:
  ..." strings sent to the model. Existing `tags={"write"}` /
  `annotations={"readOnlyHint": False}` semantics are preserved by
  forwarding `**tool_kwargs` to `mcp.tool(...)` (#74).

### Removed
- PyPI release pipeline (`.github/workflows/release.yml`) and the
  associated `scripts/smoke_install.sh` wheel smoke. The `unraid-mcp`
  name on PyPI is owned by an unrelated project; this fork is
  distributed source-only via this GitHub repo. Install via
  `uv pip install git+https://github.com/millsmillsymills/unraid-mcp.git`
  or build the Docker image locally.

### Added
- `py.typed` marker so consumers installing the wheel pick up the package's
  type information (#9).
- Startup warning when `UNRAID_USE_HTTPS=true` and `UNRAID_VERIFY_SSL=false`,
  so operators deploying outside a trusted LAN see a visible signal (#12).
- `format: password` / `writeOnly` hints on `unraid_create_user`'s `password`
  parameter so capable MCP clients can redact the value in UI (#8).
- Typed pydantic models now back every Unraid read endpoint. `UnraidClient`
  validates responses via `SystemInfo`, `ArrayState`, `ParityHistoryEntry`,
  `Disk`, `DockerContainer`, `DockerNetwork`, `Vms`, `Share`, `User`,
  `Notification`; tools return those types so FastMCP emits richer schemas
  (#6).
- `UnraidBaseModel` uses `pydantic.alias_generators.to_camel` with
  `populate_by_name=True`, so snake_case Python fields map to the Unraid
  API's camelCase shape without per-field aliases (#6).
- `make_server_lifespan(config)` factory so the lifespan is bound to the
  caller's `UnraidConfig`; `create_server(config)` is now the single source
  of truth for both mode gating and client construction (#21).
- End-to-end tool-layer tests via `fastmcp.Client` in-memory session: 51 new
  tests across all domains, covering happy path, readonly-mode invisibility,
  not-found lookups, auth errors, and unconfigured-API surfaces (#11).
- Integration test scaffolding in `tests/integration/test_live_server.py`
  with fast-skip behavior when `UNRAID_API_KEY` is not set (#23).
- `UNRAID_ALLOW_USER_MUTATIONS` feature flag (default `false`). The
  `unraid_create_user` and `unraid_delete_user` tools carry a new
  `user-mutation` tag and stay hidden unless both `UNRAID_MODE=readwrite`
  and this flag are set. Defense-in-depth via the new
  `require_user_mutation` helper (#29).
- `password_env_var` parameter on `unraid_create_user`, with a hardcoded
  `UNRAID_NEW_USER_` allowlist prefix. Lets operators keep the cleartext
  password out of MCP transcripts by reading it from a server-side env
  var instead of passing it as a tool argument (#30).
- Per-request observability in `BaseGraphQLClient`. Each round trip logs
  `graphql <operation> -> HTTP <status> in <ms>` at INFO; failures and
  HTTP >= 400 log at WARNING. Operation name comes from
  `payload.operationName` or is parsed from the GraphQL document
  (`query Foo { ... }` → `Foo`); anonymous documents log as
  `<anonymous>` (#37).
- `unraid-mcp --check-config` flag. Prints the resolved configuration
  (with the API key redacted), runs a single `validate_connection`,
  and exits 0/1/2 for success / missing key / validation failure. Lets
  operators verify their `.env` before attaching an MCP client. Also
  adds `--version` via argparse (#41).
- `unraid-mcp --version` CLI flag (#41).
- `scripts/smoke_install.sh`. End-to-end wheel smoke: `uv build` →
  install into a clean venv → exercise `--version`, `--help`, and
  `--check-config`. Catches packaging/entry-point regressions that
  `uv run pytest` against the source tree can't see (#42).
- Per-domain integration smokes in `tests/integration/test_live_server.py`
  (13 total, up from 2): one read tool per domain with invariants
  like `bridge` Docker network and `root` user. Opt-in via
  `UNRAID_API_KEY` and the `integration` marker; default `pytest`
  run still skips them all (#43).
- API-key log redaction. A `logging.Filter` attached to `httpx` /
  `httpcore` loggers at client construction time replaces the key
  with `***REDACTED***` in any log record, so enabling DEBUG-level
  HTTP tracing can't leak the `x-api-key` header. Detached on
  `client.close()`.

### Changed
- `UnraidGraphQLError` now preserves the structured fields the GraphQL spec
  guarantees: `extensions.code`, `path`, `locations`, and the raw `errors`
  list. New `UnraidValidationError` subclass surfaces
  `extensions.code == "GRAPHQL_VALIDATION_FAILED"`, and `handle_client_error`
  routes it to an actionable "upgrade unraid-mcp" tool message instead of
  dumping the raw GraphQL stack trace at the model (#69).
- **Breaking:** `UNRAID_VERIFY_SSL` now defaults to `true`. Operators using
  self-signed LAN certs must set `UNRAID_VERIFY_SSL=false` in `.env` after
  upgrade or connections will fail TLS verification (#108).
- `validate_connection()` now propagates typed `UnraidError` subclasses
  instead of returning a bool. The lifespan catches the exception, logs
  the real cause, closes the httpx client, and leaves `context.client =
  None` so tools surface `UnraidNotConfiguredError` at call time rather
  than round-tripping to a dead backend (#5).
- GraphQL errors with `extensions.code` are now routed to typed exceptions:
  `UNAUTHENTICATED` / `FORBIDDEN` → `UnraidAuthError`, `NOT_FOUND` →
  `UnraidNotFoundError`, everything else falls back to `UnraidGraphQLError`
  (#7).
- Lookup tools (`unraid_get_container`, `unraid_get_disk`, `unraid_get_share`)
  now raise `UnraidNotFoundError` on miss, surfacing through
  `handle_client_error` as `ToolError("Resource not found: ...")` rather
  than returning `{"error": "..."}` (#6).
- `handle_client_error` now passes `ToolError` through unchanged instead of
  rewrapping it as `"Unexpected error: ..."` (#26).
- `unraid_create_user` accepts `password` xor `password_env_var` (previously
  `password` was required and positional). Existing inline-password callers
  are unchanged; the default path is unchanged (#30).
- `validate_connection` now bypasses the `tenacity` retry loop and uses a
  5-second timeout, so a typo'd `UNRAID_HOST` fails in seconds instead of
  blocking startup for up to ~90s (#34).
- `UnraidConfig.api_enabled` now treats empty-string `UNRAID_API_KEY` as
  unconfigured (previously only `None` did). Prevents `UNRAID_API_KEY=`
  in a shell from pretending the server was configured (#41).
- Pre-commit hooks now run `ruff` and `mypy` via `uv run` (`language: system`)
  so pre-commit and CI share one toolchain, eliminating version drift
  between pinned hook revs and `pyproject.toml`'s dev extras (#10).
- `CLAUDE.md` tool layout diagram updated to match the flat `tools/*.py`
  structure instead of fictional per-domain subdirectories (#22).

### Coverage / quality
- Unit tests: 66 → 161 passing.
- Integration smokes: 2 → 13 (opt-in).
- Coverage: 49% → 85% overall; `fail_under` raised from 40 to 80.
- Tool-layer coverage: 29–48% → 66–93%.
- Models: 0% used → 100% integrated.
- Wheel smoke (`scripts/smoke_install.sh`) covers build + install +
  CLI invocation.

## [0.1.0] - 2026-04-18

Initial scaffold. Production-grade FastMCP server for the Unraid GraphQL API,
with 38 tools across system, array, parity, disks, docker, VMs, shares,
users, and notifications domains. Read/write mode separation, typed error
hierarchy, strict mypy + broad ruff ruleset, 66 unit tests, Apache-2.0
licensed.
