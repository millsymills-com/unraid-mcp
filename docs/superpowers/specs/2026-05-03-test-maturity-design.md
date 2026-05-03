# Test Maturity Uplift — Design Spec

**Status:** approved (brainstorming)
**Date:** 2026-05-03
**Owner:** mills
**Related:** PR #68 (startup schema check)

## Problem

`unraid-mcp` ships to PyPI with a 183-test unit suite plus a small read-only
integration suite, an 80% coverage gate, and a one-shot `tests/integration_live.py`
probe. Gaps that block higher confidence:

- Write tools (mutations) have **zero live coverage** — they are only mocked.
- The MCP transport layer (FastMCP wiring, JSON-RPC over stdio) is not exercised
  end-to-end. Mode-gating is asserted only at the in-process level.
- Schema drift is detected only at runtime startup (PR #68); breaking changes in
  the Unraid GraphQL API are not surfaced at PR-review time.
- Pure functions (parsers, error mapping, config validation) have no
  property-based fuzzing.
- Test environment isolation leaks (a unit test currently fails because
  `~/Desktop/Projects/.env` bleeds into a `monkeypatch.delenv` test).
- No registry that proves every MCP tool has at least one corresponding live
  test; coverage of new tools depends on contributor discipline.

The goal is to raise this from "credible unit suite" to "every tool exercised
against a real Unraid server, with breaking-change detection at PR time."

## Goals

- **Branch coverage ≥ 90%** across the project; ≥ 95% on `clients/` and `tools/`.
- **Every read tool live-tested** against the live Unraid server.
- **Every low- and medium-blast-radius write tool live-tested**, with explicit
  multi-layer gating, no possibility of accidental destruction outside
  `mcptest_*`-prefixed assets.
- **PR-time schema drift detection** in addition to the runtime check.
- **MCP transport tested end-to-end** over real stdio JSON-RPC.
- **Property-based tests** on parsers, config, and error-mapping.
- **A registry-driven proof** that every tool is live-tested or explicitly waived.

## Non-Goals

- Mutation testing (`mutmut` / `cosmic-ray`) — filed as a follow-up issue.
- Performance or load testing.
- Disruptive write coverage: array stop, VM force-stop, container delete. The
  blast radius outweighs the value at this maturity step.
- CI execution of live tests. Live tests are local-only by user decision; CI
  continues to run unit + property + e2e + `test_used_surface` only.
- Visual coverage-trend dashboards.

## Constraints

- Live tests target the user's production tower (`resurgent.local`). Reads are
  always safe; writes are gated and limited to `mcptest_*`-prefixed assets.
- Unraid GraphQL has no `docker create` or `vm create` mutations, so test
  containers and VMs cannot be created by tests. They are set up once by the
  user via the Unraid UI; fixtures auto-discover them and skip cleanly when
  absent.
- Test users created by tests are deleted by the same test's finalizer.
- All live tests are gated such that an unauthorized run is impossible: marker
  + env flag + per-domain sub-gates.

## Architecture

### Suite layout

```
tests/
├── conftest.py                # env loader, env-isolation autouse, live_client
├── unit/                      # existing — no structural change
├── property/                  # NEW — Hypothesis tests on pure functions
├── integration/               # existing read-only live tests, expanded to all read tools
│   └── _coverage.py           # NEW — per-tool live-coverage manifest
├── live_write/                # NEW — gated mutating live tests
│   ├── conftest.py            # write-gate, mcptest_* asset discovery, serial enforcement
│   ├── test_notifications.py
│   ├── test_parity.py
│   ├── test_users.py
│   ├── test_docker.py         # uses discovered mcptest-container
│   └── test_vms.py            # uses discovered mcptest-vm
├── e2e/                       # NEW — MCP stdio transport round-trip
│   ├── conftest.py            # subprocess spawner, mock GraphQL endpoint
│   └── test_stdio_handshake.py
└── contract/                  # NEW — GraphQL schema snapshot + drift detection
    ├── snapshot.graphql
    ├── snapshot.sha256
    ├── refresh.py             # one-shot: re-snapshot from live server
    ├── test_used_surface.py   # parses queries vs snapshot — no live env needed
    └── test_schema_drift.py   # diffs live SDL against snapshot — local only
```

`tests/integration_live.py` (the existing one-shot probe) is retained as a
manual debugging tool. It is not part of the pytest suite and is unaffected by
this change.

### Markers

Configured in `pyproject.toml`:

| Marker | Default-run? | Env required |
|---|---|---|
| `integration` | no | `UNRAID_API_KEY` |
| `live_write` | no | `UNRAID_API_KEY` + `UNRAID_ALLOW_LIVE_WRITES=1` |
| `e2e` | yes | none (mock backend) |
| `contract` | partial | `test_schema_drift` requires `UNRAID_API_KEY`; `test_used_surface` does not |
| `property` | yes | none |
| `slow` | yes | none |

`addopts` in `[tool.pytest.ini_options]` defaults to `-m "not integration and not live_write and not (contract and requires_live)"` so the default `pytest` invocation runs unit + property + e2e + the no-env contract test.

### Execution paths

| Command | Purpose | Time budget |
|---|---|---|
| `uv run pytest` | every commit, CI | < 30 s |
| `uv run pytest -m integration` | live read smokes (local) | < 60 s |
| `uv run pytest -m live_write` (+ env flag) | live write smokes (local, manual) | < 3 min |
| `uv run pytest -m contract` (live) | pre-release schema drift check | < 15 s |
| `uv run python -m tests.contract.refresh` | re-snapshot when drift is intentional | < 5 s |

## Components

### 1. Live-write gating (defense in depth)

Three layers; all must pass before any mutation runs.

1. **Marker** — `pytest.mark.live_write`, skipped unless `-m live_write` is passed.
2. **Env flag** — `UNRAID_ALLOW_LIVE_WRITES=1`. An autouse session fixture in
   `tests/live_write/conftest.py` calls `pytest.skip(...)` if the flag is unset.
3. **Per-domain sub-gates** for sensitive ops:
   - `UNRAID_ALLOW_USER_MUTATIONS=1` (already exists in `src/`) — required for
     create/delete user tests.

The `mcptest_*` invariant is enforced as a hard guard: every write fixture
asserts the target asset's name starts with `mcptest` before any mutation. A
discovered asset that doesn't match raises `RuntimeError`, never a soft
fallback. This makes accidental writes against non-test assets structurally
impossible.

A pre-flight banner prints the live host, the mutation classes that will run,
and the assets that will be touched, then sleeps 3 s before collection. Loud,
interruptible.

Live-write tests run **serially**: a `pytest_collection_modifyitems` hook in
`tests/live_write/conftest.py` adds `pytest.mark.serial` and refuses to run
under `pytest-xdist` workers. Parallel writes against one tower are unsafe.

### 2. Asset lifecycle

| Asset | Origin | Cleanup |
|---|---|---|
| `mcptest_user_<uuid8>` | test creates via `unraid_create_user` | finalizer calls `unraid_delete_user`; wrapped in `try/except` so a failed test still tears down |
| `mcptest-container` | one-time manual setup (Unraid UI: Docker → Add Container, image `nginx:alpine`) | tests only start/stop/pause/restart; never delete |
| `mcptest-vm` | one-time manual setup (Unraid UI: VMs → Add VM, minimal config) | tests only pause/resume/reboot; never delete or force-stop |
| Notifications | created by test using existing notification flow | archive then delete in finalizer |
| Parity check | started by test | `cancel` in finalizer always |

Discovery fixtures in `tests/live_write/conftest.py` query the live server for
`mcptest_*`-prefixed assets and `pytest.skip` with setup instructions if
absent. The skip message includes the exact UI steps to create the asset.

A `pytest_sessionfinish` hook re-queries the tower for `mcptest_*` users,
unarchived `mcptest_*` notifications, and active parity checks; warns about
orphans with the exact GraphQL command needed to clean them up. It never
auto-deletes — the human decides.

### 3. Schema contract pinning

`tests/contract/refresh.py` issues a GraphQL introspection query, walks
`clients/unraid.py` for every `_QUERY_*` and `_MUTATION_*` constant, parses
them as GraphQL documents, computes the **referenced types and fields**, and
writes a focused, pretty-printed SDL to `snapshot.graphql` plus a sha256 to
`snapshot.sha256`. Both files are committed.

`tests/contract/test_used_surface.py` (no live env needed):
- Parses `snapshot.graphql` and every query/mutation constant in
  `clients/unraid.py`.
- Asserts every field referenced in a query exists in the snapshot.
- Asserts every input variable's type matches.
- Catches typos and drift between client code and the pinned schema in default
  CI.

`tests/contract/test_schema_drift.py` (local, requires `UNRAID_API_KEY`):
- Fetches live SDL via introspection.
- Fast path: hash equality check via `snapshot.sha256`.
- On mismatch, parses both with `graphql-core` (already a transitive dep) and
  diffs at AST level:
  - **Breaking** (test fails): removed type/field, narrowed type
    (e.g. nullable → non-null on input), removed enum value, changed field arg type.
  - **Additive** (test xfails with informational message): new type/field/enum
    value, widened nullability. Not a failure — a signal to refresh the
    snapshot when convenient.
- Diff output is human-readable: `Field 'Container.id' changed type ID! → String!`.

### 4. MCP transport / E2E

`tests/e2e/test_stdio_handshake.py` spawns `unraid-mcp` as a subprocess via
`fastmcp.Client` + `StdioTransport`. Environment points at a local mock
GraphQL endpoint (`pytest-httpserver` or `respx` ASGI app) that responds with
canned introspection + a few fixture responses. No live Unraid required, so
e2e runs in default CI.

Test cases (small, high-signal):

1. **Handshake & list_tools** — connect, call `list_tools`, assert every
   expected tool name is present, assert tool count matches `register_all_tools`
   registration count.
2. **Read tool round-trip** — call `unraid_get_info`, assert structured content
   matches mock GraphQL response.
3. **Write tool exists in rw mode** — start subprocess with
   `UNRAID_MODE=readwrite`, assert `unraid_start_container` is in the tool list.
4. **Write tool hidden in readonly** — default mode, assert
   `unraid_start_container` is **not** in the tool list. Catches mode-gating
   leaks (the most security-relevant invariant in the server).
5. **Tool errors surface as MCP errors** — mock a GraphQL error; assert client
   receives `ToolError` with the expected message shape.
6. **Lifespan completes** — server starts, advertises capabilities, shuts down
   cleanly on stdin close.

Subprocess spawn cost ~1-2 s; suite budget < 15 s with shared session fixture
where possible.

### 5. Property-based tests

`tests/property/` uses `hypothesis`. Targets are pure functions where edge
cases hide:

1. **`UnraidConfig` env parsing** (`src/unraid_mcp/config.py`)
   - `@given(st.text())` for `UNRAID_HOST` — never crashes; either parseable
     URL or `ValidationError` with field reference.
   - Property: parse → re-serialize → parse is idempotent.
   - Property: `is_readwrite` is true iff `UNRAID_MODE` casefolds to `readwrite`.

2. **GraphQL error → exception mapping** (`errors.py` + `clients/base.py`)
   - `@given(st.lists(st.fixed_dictionaries({...})))` — mapper always returns a
     subclass of `UnraidError`, never raises, never returns `None`.
   - Empty errors list never produces an exception; non-empty always does.
   - Extension code `UNAUTHENTICATED` always maps to `UnraidAuthError`
     regardless of message text.

3. **Pydantic model tolerance** (`models/*.py`)
   - `@given(st.dictionaries(st.text(), st.from_type(JsonValue)))` — round-trip
     arbitrary JSON-shaped dicts through models that use `extra="allow"`. No
     field stripping for known fields, no crash on unknown fields.

4. **Tool argument validation** (`tools/users.py` `password_env_var`)
   - `@given(st.text())` for env var names — only names matching
     `UNRAID_USER_PW_*` accepted; everything else rejected with `ToolError`
     naming the prefix.

Hypothesis profiles: `default` with `max_examples=50` for fast local runs;
`ci` with `max_examples=200` enabled via `HYPOTHESIS_PROFILE=ci`. Database in
`.hypothesis/examples/`, gitignored.

### 6. Per-tool live-coverage registry

`tests/integration/_coverage.py` is a manifest:

```python
@dataclass(frozen=True)
class ToolCoverage:
    name: str
    reads: bool
    writes: bool
    marker: str | None              # None = waived
    needs_asset: str | None = None  # "mcptest_container", "mcptest_vm", ...
    extra_gate: str | None = None   # env var name
    skip_reason: str | None = None  # required if marker is None

TOOLS = [
    ToolCoverage("unraid_get_info",            reads=True,  writes=False, marker="integration"),
    ToolCoverage("unraid_list_containers",     reads=True,  writes=False, marker="integration"),
    ToolCoverage("unraid_start_container",     reads=False, writes=True,  marker="live_write", needs_asset="mcptest_container"),
    ToolCoverage("unraid_create_user",         reads=False, writes=True,  marker="live_write", extra_gate="UNRAID_ALLOW_USER_MUTATIONS"),
    ToolCoverage("unraid_stop_array",          reads=False, writes=True,  marker=None,         skip_reason="disruptive — out of scope"),
    # … one row per registered MCP tool …
]
```

Two meta-tests enforce the manifest:

- `test_every_registered_tool_is_in_manifest` — walks the FastMCP tool registry,
  asserts every tool name appears in `TOOLS`. Fails when a new tool is added
  without a manifest entry.
- `test_every_manifest_tool_has_a_live_test` — for each `TOOLS` entry with a
  non-None `marker`, walks pytest's collected tests and asserts at least one
  test ID matches `tests/{integration|live_write}/test_<domain>.py::*` and
  references the tool name. Fails when a manifest entry has no corresponding
  test.

## Data flow

### Default `pytest` (every commit, CI)

```
unit/           → in-process, respx/monkeypatch mocks
property/       → in-process, Hypothesis fuzz (50 examples local, 200 CI)
e2e/            → spawns unraid-mcp subprocess, mock GraphQL via pytest-httpserver
contract/       → only test_used_surface.py (parses snapshot + queries, no I/O)
```

No env vars needed. < 30 s.

### `pytest -m integration` (local, on demand)

```
integration/    → real GraphQL over HTTPS, read tools only
                  same client config as production
```

Requires `UNRAID_API_KEY`, `UNRAID_HOST`. < 60 s.

### `pytest -m live_write` + `UNRAID_ALLOW_LIVE_WRITES=1`

```
pre-flight banner → 3s sleep → collection → serial execution
per-domain fixture: discover or create mcptest_* asset
test: read state → assert preconditions → mutate → re-read → assert postconditions
finalizer: reverse mutation; tear down created assets
session-end: orphan scan, warn with cleanup commands
```

< 3 min.

### `pytest -m contract` (local, pre-release)

```
fetch live SDL → hash check → if mismatch, AST diff → categorize breaking vs additive
```

Requires `UNRAID_API_KEY`. < 15 s.

### State-via-re-read pattern (live_write)

```python
async def test_pause_container_changes_state(mcptest_container, live_client):
    before = await live_client.get_container(mcptest_container.id)
    assume_running(before)
    await live_client.pause_container(mcptest_container.id)
    after = await wait_for_state(
        lambda: live_client.get_container(mcptest_container.id),
        predicate=lambda c: c.state == "paused",
        timeout=5, interval=1,
    )
    assert after.state == "paused"
    # finalizer: unpause
```

Assertions are on observable server state, not on the mutation's return value.
Catches silent no-op mutations and schema regressions where the mutation
returns the old shape but didn't actually do anything.

## Error handling

### Failure taxonomy

Every failure falls into exactly one bucket. Fixtures classify; messages
include the next action.

| Category | Cause | Behavior | Exit signal |
|---|---|---|---|
| `assertion` | code under test produced wrong result | standard `AssertionError` with full diff | non-zero |
| `env_missing` | required var unset | `pytest.skip` naming the exact var | 0 (skipped) |
| `asset_missing` | `mcptest-container` / `mcptest-vm` not present | `pytest.skip` with inline UI setup steps | 0 (skipped) |
| `live_unreachable` | can't reach `UNRAID_HOST` | first failure marks all live tests `errored`; subsequent fail-fast skip | 1 |
| `schema_mismatch` | live SDL drifted from snapshot | human-readable diff (`Field X.y removed`); fail with category tag | 1 |
| `flake_suspect` | live op succeeded but state re-read disagrees within tolerance window | single retry with 2 s delay; if still wrong, fail with `flake_suspect` tag and timing info | 1 |
| `cleanup_failed` | finalizer couldn't tear down `mcptest_*` asset | session-end summary lists orphans; warning unless test also failed | conditional |

### Retry policy

Narrow and explicit. No blanket `@pytest.mark.flaky`.

- **Network-layer transient** (`httpx.ConnectError`, `httpx.ReadTimeout` while
  reading): handled by existing `tenacity` config in `BaseGraphQLClient`. No
  test-level retry on top.
- **State-read after write**: single 2 s retry via `wait_for_state(predicate,
  timeout=5s, interval=1s)` helper. Implemented per-call, not as a generic
  marker.
- **Nothing else retries.** Schema mismatches, assertions, auth failures fail
  immediately.

### Cleanup discipline

- Every `mcptest_*` create registers a finalizer **before** the create call
  returns. Finalizer runs even if the create's assert fails.
- Finalizer wraps cleanup in `try/except Exception` and records to a
  session-level orphan list. Re-raising would mask the real test failure.
- `pytest_sessionfinish` re-queries the tower for `mcptest_*` orphans and
  prints exact GraphQL commands to clean them up. Never auto-deletes.

### Message quality bar

Every fixture skip/fail message answers "what do I do next?" in one line.

- Bad: `skipping: env not set`
- Good: `skipping live_write: set UNRAID_ALLOW_LIVE_WRITES=1 to enable (writes against https://resurgent.local)`
- Bad: `mcptest-container not found`
- Good: `skipping docker write tests: create container named mcptest-* on tower (Docker tab → Add Container, image=nginx:alpine)`

### Pre-existing env-leak bug

`tests/unit/test_main.py::TestCheckConfig::test_no_api_key_exits_one` currently
fails because the suite leaks `UNRAID_API_KEY` from
`~/Desktop/Projects/.env`. Fix as part of this work: a top-level
`tests/conftest.py` autouse fixture isolates `UNRAID_*` env vars per test;
integration / live_write tests opt back in via explicit `live_env` fixture.
This is the maturity floor — without it, every env-driven test is suspect.

## Testing strategy

### Dimension matrix — what each layer guarantees

| Layer | Catches | Doesn't catch | Default `pytest`? | Live env? |
|---|---|---|---|---|
| **unit** | logic in pure helpers, mode-gating, tool argument plumbing | schema drift, transport bugs, real-world data shapes | yes | no |
| **property** | edge cases in parsers, error-mapping, config; round-trip invariants | semantic correctness against real Unraid | yes | no |
| **e2e** | FastMCP wiring, JSON-RPC serialization, mode-gating across stdio | actual GraphQL behavior | yes | no (mock) |
| **contract** | schema drift, query-references-missing-field typos | runtime tool behavior | yes (`test_used_surface` only) | partial |
| **integration** | read tool round-trip with real data shapes | mutation correctness | no | yes (read) |
| **live_write** | mutation correctness, observable state changes, cleanup | non-mcptest assets, disruptive ops | no | yes (write) |

Each layer is necessary and not redundant.

### Coverage targets per module

| Module | Branch coverage gate | Rationale |
|---|---|---|
| `clients/base.py` | 95% | retry / error / transport — core invariant code |
| `clients/unraid.py` | 90% | mostly typed wrappers; some defensive paths hard to hit |
| `tools/*.py` | 95% | thin shims; nearly all branches reachable |
| `errors.py` | 100% | tiny module, fully exercisable |
| `config.py` | 95% | env parsing — every branch via property tests |
| `models/*.py` | 85% | `extra="allow"` paths and validators only |
| `server.py`, `__main__.py` | 80% | bootstrap, partial coverage acceptable |
| **project floor** | **90%** | raised from current 80% |

Enforced via `tool.coverage.report.fail_under` plus per-file thresholds. If
`coverage.py`'s native per-file gate is insufficient, a `make coverage` target
runs scoped invocations and aggregates results.

### Layer interactions

- **unit + e2e** both touch mode-gating from different angles. unit asserts
  `mcp.disable(tags={"write"})` was called; e2e asserts gated tools genuinely
  don't appear over stdio. Either alone is insufficient.
- **integration + contract** both touch the live API. integration is breadth
  (every read tool round-trips); contract is shape (every field used exists
  with the expected type). Contract failures explain integration failures.
- **property + unit** on `errors.py`: unit asserts named exceptions; property
  asserts the *invariant* (always-typed, never-raises) across many inputs.
- **live_write + integration** share the `live_client` fixture; live_write
  performs a write then calls integration-style reads to verify.

### Goal scoreboard (acceptance criteria)

| Criterion | Today | Target |
|---|---|---|
| Branch coverage (project) | 80% gate; actual unmeasured (suite stops on env-leak failure) | ≥ 90% measured |
| Tools with at least one unit test | all | all |
| Read tools with at least one live test | partial | all |
| Write tools (low+medium tier) with at least one live test | 0 | all in scope |
| Disruptive write tools live-tested | 0 | 0 (waived in registry) |
| Schema drift detection | runtime only | PR-time + runtime |
| MCP transport tested end-to-end | no | yes |
| Property tests on parsers/config/error-map | no | yes |
| Env isolation between tests | leaky | autouse isolator |
| Hypothesis examples in CI | n/a | 200 per property |
| Mutation testing | n/a | filed as future issue |

## Dependencies

New runtime deps: none.

New dev deps:

- `hypothesis` — property-based testing.
- `pytest-httpserver` — local HTTP mock for the e2e GraphQL endpoint. The
  subprocess-spawned MCP server can't share an in-process `respx` mock, so a
  real local listener is required.
- `graphql-core` — schema parsing and AST diff for `tests/contract/`. New
  direct dev dep (not transitively available via the existing dep tree).

## Rollout

The implementation plan (next step, via writing-plans skill) will sequence the
work; this spec only defines what gets built.

## Open questions

None at design time. The implementation plan will surface concrete questions
as it sequences work.
