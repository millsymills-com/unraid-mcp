# CLAUDE.md — Project Intelligence for unraid-mcp

## Project Overview

Production-grade Python MCP server for the Unraid GraphQL API. Distributed source-only via this GitHub repo; install with `uv pip install git+https://github.com/millsymills-com/unraid-mcp.git`. Uses FastMCP framework with declarative read/write mode separation. Talks to a single GraphQL endpoint at `https://{host}:{port}/graphql` authenticated by `x-api-key`.

## Commands

```bash
# Install (development)
uv sync --extra dev

# Lint
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Type check
uv run ty check src/unraid_mcp/

# Test (unit only, excludes integration)
uv run pytest tests/unit/ -v

# Test with coverage
uv run pytest tests/unit/ --cov=unraid_mcp --cov-report=term-missing -m "not integration"

# Integration tests (requires live Unraid server)
uv run pytest tests/integration/ -v -m integration

# Security scan
uv run bandit -r src/unraid_mcp/ -c pyproject.toml

# Pre-commit hooks
uv run pre-commit run --all-files

# Build package
uv build

# Pre-flight schema compatibility against a live Unraid server
uv run unraid-mcp --check-schema
```

## Architecture

```
src/unraid_mcp/
├── __init__.py          # Package root, exports __version__
├── __main__.py          # Entry point: creates and runs server
├── server.py            # FastMCP server creation + lifespan
├── config.py            # Pydantic settings (env vars)
├── errors.py            # Exception hierarchy + error mapping
├── clients/             # GraphQL clients (httpx async)
│   ├── base.py          # BaseGraphQLClient with retry/auth/error mapping
│   └── unraid.py        # UnraidClient with typed query/mutation methods
├── models/              # Pydantic response models (extra="allow")
│   ├── common.py        # Shared types
│   ├── system.py        # System / OS / CPU / memory
│   ├── array.py         # Array + parity
│   ├── disks.py         # Disk
│   ├── docker.py        # Containers + networks
│   ├── vms.py           # Virtual machines
│   ├── shares.py        # User and disk shares
│   ├── users.py         # Unraid users
│   └── notifications.py # Notifications
└── tools/               # MCP tool definitions (flat — one module per domain)
    ├── _helpers.py      # shared context/client guards
    ├── system.py        # info / flash / registration / connect
    ├── array.py         # get_array, start/stop array
    ├── parity.py        # parity history + start/pause/resume/cancel
    ├── disks.py         # list / get disk
    ├── docker.py        # list / get container, list networks, start/stop/restart/pause/unpause
    ├── vms.py           # list / start / stop / force_stop / pause / resume / reboot
    ├── shares.py        # list / get share
    ├── users.py         # get_me (Unraid 7.2+ dropped Query.users/addUser/deleteUser)
    └── notifications.py # list / archive / delete / archive_all
```

## Conventions

- **Python >=3.13**, strict ty, ruff for lint+format
- **Line length**: 120 characters
- **Tool naming**: `unraid_{verb}_{entity}` (e.g., `unraid_list_containers`, `unraid_start_array`)
- **Write tools**: Tagged with `{"write"}`, annotated with `readOnlyHint=False`. Disabled in readonly mode via `mcp.disable(tags={"write"})`
- **Defense-in-depth**: Write tools also check `config.is_readwrite` at runtime
- **Models**: Use `extra="allow"` to tolerate unknown fields from the Unraid API
- **Client**: Single `UnraidClient` wraps GraphQL `query`/`mutate` calls; uses `httpx.AsyncClient` with `tenacity` retry (3 attempts, exponential backoff)
- **Error mapping**: GraphQL errors -> typed exceptions -> `ToolError` with agent-readable messages
- **Tests**: Use `respx` for HTTP mocking, `pytest-asyncio` for async tests
- **No print statements**: Use `logging` module (enforced by ruff T20 rule)

## Key Patterns

### Mode Gating
```python
# Tools tagged with {"write"} are disabled in readonly mode
@mcp.tool(tags={"write"}, annotations={"readOnlyHint": False})
async def unraid_start_container(...): ...

# In create_server:
if not config.is_readwrite:
    mcp.disable(tags={"write"})
```

### Graceful Degradation
```python
# Server still starts even when API key is missing — tools simply
# fail at call time with a clear "API not configured" message.
if config.api_enabled:
    register_all_tools(server)
```

### GraphQL Transport
```python
# All operations go through one endpoint
result = await client.query(QUERY_INFO)
result = await client.mutate(MUTATION_START_CONTAINER, variables={"id": container_id})
```

## CI/CD

- **CI**: Runs on push to main and PRs. Lint (ruff) + typecheck (ty) + test (pytest) on Python 3.13.
- **Security**: Weekly Bandit scans + dependency review on PRs
- **Dependabot**: Weekly updates for Python deps (uv ecosystem), GitHub Actions, and Docker base images

## Canonical MCP standards

Authoritative source: `~/Desktop/Projects/consistency-check/docs/standards/`. This repo is graded against `mcp.md` + the language-specific file (`python.md` for Python repos, `go.md` for Go) + `mcp-protocol.md`.

Run the audit:

```bash
cd ~/Desktop/Projects/consistency-check
uv run consistency-check audit --repo $(basename "$PWD")
```

## Agent skills

### Issue tracker

GitHub Issues via `gh` CLI (repo inferred from `git remote -v`). See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical names — `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. Categories: `bug`, `enhancement`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: `CONTEXT.md` + `docs/adr/` at repo root (created lazily by `/grill-with-docs`). See `docs/agents/domain.md`.
