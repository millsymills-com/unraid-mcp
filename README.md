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

Once configured, run `unraid-mcp --check-config` to verify connectivity before attaching an MCP client — it prints the resolved config (with the API key redacted), runs a single validation query, and exits 0 / 1 / 2 (ok / no key / validation failed).

## MCP client setup

`unraid-mcp` speaks MCP over stdio. Point any compatible client at the installed console script and pass your Unraid settings through the `env` block.

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```jsonc
{
  "mcpServers": {
    "unraid": {
      "command": "unraid-mcp",
      "env": {
        "UNRAID_HOST": "tower.local",
        "UNRAID_API_KEY": "your-key-here",
        "UNRAID_MODE": "readonly"
      }
    }
  }
}
```

If you installed from source into a venv, use the venv's python explicitly:

```jsonc
{
  "mcpServers": {
    "unraid": {
      "command": "/path/to/.venv/bin/unraid-mcp",
      "env": { "UNRAID_HOST": "tower.local", "UNRAID_API_KEY": "your-key-here" }
    }
  }
}
```

### Cursor

Edit `~/.cursor/mcp.json` (or via **Settings → MCP → Add new MCP Server**):

```jsonc
{
  "mcpServers": {
    "unraid": {
      "command": "unraid-mcp",
      "env": {
        "UNRAID_HOST": "tower.local",
        "UNRAID_API_KEY": "your-key-here"
      }
    }
  }
}
```

### Continue.dev

In `.continue/config.json`:

```jsonc
{
  "experimental": {
    "modelContextProtocolServers": [
      {
        "transport": {
          "type": "stdio",
          "command": "unraid-mcp",
          "env": {
            "UNRAID_HOST": "tower.local",
            "UNRAID_API_KEY": "your-key-here"
          }
        }
      }
    ]
  }
}
```

### Claude Code (terminal)

```bash
claude mcp add unraid -- unraid-mcp
```

Then set env vars in the same shell, or use `claude mcp add unraid --env UNRAID_HOST=tower.local --env UNRAID_API_KEY=...`.

### Enabling write tools

The server starts in read-only mode by default. To expose the `start/stop/restart` family, set `UNRAID_MODE=readwrite` in the client's `env` block. To additionally expose `unraid_create_user` / `unraid_delete_user`, also set `UNRAID_ALLOW_USER_MUTATIONS=true` — these are double-gated because they modify OS-level accounts.

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
| `UNRAID_ALLOW_USER_MUTATIONS` | `false` | Secondary switch for `unraid_create_user` / `unraid_delete_user`; even in `readwrite` mode these stay hidden unless this is `true` |
| `UNRAID_NEW_USER_*` | — | When set, can be referenced via `password_env_var` on `unraid_create_user` so the password stays out of MCP transcripts. Name must start with `UNRAID_NEW_USER_`. |

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
