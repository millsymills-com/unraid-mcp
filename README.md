# unraid-mcp

Production-grade Python MCP server for the Unraid GraphQL API.

## Status

**Under active development** — see [CLAUDE.md](CLAUDE.md) for the architectural overview.

## Features

- **MCP tools** covering Unraid system info, array, disks, Docker, VMs, shares, users, notifications, and parity checks
- **Read/write mode separation** — write tools invisible in readonly mode (`mcp.disable(tags={"write"})`) with runtime defense-in-depth
- **Single-endpoint GraphQL client** — `httpx` async client over the Unraid `/graphql` endpoint with `tenacity` retry and typed error mapping
- **Typed, linted, tested** — strict mypy, ruff, pytest with CI across Python 3.11–3.13

## Quick Start

```bash
# Install from PyPI (once published)
uv pip install unraid-mcp

# Or install from source
git clone https://github.com/millsmillsymills/unraid-mcp.git
cd unraid-mcp
uv sync

# Configure
cp .env.example .env
# Edit .env with your Unraid host and API key

# Run
unraid-mcp
```

Generate an API key in the Unraid WebGUI under **Settings → Management Access → API Keys**, or from a terminal on the server with `unraid-api apikey --create`. Enable the GraphQL API the first time via **Settings → Management Access → Developer Options**.

## Configuration

See [.env.example](.env.example) for all configuration options.

| Variable | Default | Description |
|----------|---------|-------------|
| `UNRAID_MODE` | `readonly` | `readonly` or `readwrite` |
| `UNRAID_HOST` | `tower.local` | Unraid server hostname or IP |
| `UNRAID_PORT` | `443` | HTTPS port for the API |
| `UNRAID_USE_HTTPS` | `true` | Use HTTPS (set false for plain HTTP) |
| `UNRAID_API_KEY` | — | API key from Unraid WebGUI |
| `UNRAID_VERIFY_SSL` | `false` | Verify TLS cert (false for self-signed) |

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Lint and format
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Type check
uv run mypy src/unraid_mcp/

# Test
uv run pytest tests/unit/ -v

# Pre-commit hooks
uv run pre-commit install
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
