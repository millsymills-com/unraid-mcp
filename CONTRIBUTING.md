# Contributing to unraid-mcp

Thanks for your interest in improving `unraid-mcp`. This document covers the development workflow, coding standards, and how to get a change merged.

## Development Setup

```bash
git clone https://github.com/millsmillsymills/unraid-mcp.git
cd unraid-mcp
uv sync --extra dev
uv run pre-commit install
```

Copy `.env.example` to `.env` and fill in the host and API key for your Unraid server. The server still starts when the key is unset — tool calls then fail with a clear "API not configured" message.

## Workflow

1. Fork the repo, or create a branch in the main repo if you have commit access.
2. Make your changes, keeping commits focused and well-described.
3. Run the local gates (below). CI runs the same gates on push.
4. Open a PR against `main` with a short summary of what changed and why.

## Local Quality Gates

All checks must pass locally before you push:

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/unraid_mcp/
uv run pytest tests/unit/ -v
```

For security-sensitive changes also run:

```bash
uv run bandit -r src/unraid_mcp/ -c pyproject.toml
```

For release-shaped changes (packaging, entry point, dependency versions) run the wheel smoke:

```bash
bash scripts/smoke_install.sh
```

It runs `uv build`, installs the wheel into a clean venv, and exercises
`unraid-mcp --version`, `--help`, and `--check-config` to catch
packaging and entry-point regressions the in-repo test suite doesn't.
Requires `python3`, `unzip`, and a working `uv` on `PATH`.

## Coding Standards

- **Python >=3.11**, strict `mypy`, `ruff` for lint and format.
- **Line length**: 120 characters.
- **No print statements** — use the `logging` module (enforced by ruff T20).
- **Models** use `extra="allow"` to tolerate unknown fields from the Unraid API.
- **Client** uses `httpx.AsyncClient` with `tenacity`-based retry.
- **Errors** propagate as typed `UnraidError` subclasses; tool layer maps them to `ToolError`.

## Tool Naming and Registration

- Tool names follow `unraid_{verb}_{entity}` (e.g., `unraid_list_containers`, `unraid_start_array`).
- Write tools must be tagged `tags={"write"}` and annotated `readOnlyHint=False`.
- Write tools must also check `config.is_readwrite` inside the function body (defense-in-depth).
- Destructive tools (delete, archive, stop, etc.) should also carry `destructiveHint: True`.

## Testing

- Unit tests use `pytest` + `pytest-asyncio` + `respx` for HTTP mocking.
- Integration tests live under `tests/integration/` and require a live Unraid server. Mark them with `@pytest.mark.integration`.
- When adding a tool, add at least one happy-path test and one error-path test. Cover mode gating for any write tool.

## Commits and PRs

- Write commit messages in the Conventional Commits style (`feat:`, `fix:`, `docs:`, `deps:`, `chore:`, etc.).
- Keep PRs small where possible. Large refactors are easier to review when split into sequenced commits.
- Reference the relevant plan, issue, or requirement ID in the PR body when it applies.
- Add a one-line entry under `[Unreleased]` in [`CHANGELOG.md`](CHANGELOG.md) for any user-visible change (new tool, new env var, new error mapping, behavior change, security fix). Internal refactors that don't change behavior or surface area can be skipped.

## Releases

Releases are cut by tagging `v*` on `main`. CI builds with `uv build`, publishes to TestPyPI, and then promotes to PyPI via trusted publishing. Maintainers own the tag step — contributors should not tag releases directly.

## Reporting Security Issues

Please do not open public issues for security-sensitive bugs. Email the maintainers directly (see repository metadata) so we can assess and patch before public disclosure.
