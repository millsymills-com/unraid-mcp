# Changelog

All notable changes to `unraid-mcp` are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
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
- End-to-end tool-layer tests via `fastmcp.Client` in-memory session — 51 new
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
  (13 total, up from 2) — one read tool per domain with invariants
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

## [0.1.0] — 2026-04-18

Initial scaffold. Production-grade FastMCP server for the Unraid GraphQL API,
with 38 tools across system, array, parity, disks, docker, VMs, shares,
users, and notifications domains. Read/write mode separation, typed error
hierarchy, strict mypy + broad ruff ruleset, 66 unit tests, Apache-2.0
licensed.
