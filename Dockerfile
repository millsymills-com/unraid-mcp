# Minimal runtime image for unraid-mcp.
#
# Built for stdio-transport use from MCP clients. Invoke via:
#
#     docker run -i --rm \
#         -e UNRAID_HOST=tower.local \
#         -e UNRAID_API_KEY=your-key \
#         ghcr.io/millsymills-com/unraid-mcp:latest
#
# The `-i` (keep stdin open) flag is required — MCP clients attach to
# stdin/stdout. Use `--rm` so each client connection starts fresh.

ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim AS base

# uv provides fast, reproducible dep resolution and pulls the pinned
# versions from uv.lock. Pinned to an explicit tag so image rebuilds
# stay reproducible (Dependabot keeps this current).
COPY --from=ghcr.io/astral-sh/uv:0.11.9 /uv /uvx /usr/local/bin/

# Run as a non-root user so the container doesn't need to bind to a
# privileged uid. Unraid typically maps container uids to its own
# users, but 1000 is the historical default.
RUN groupadd --system --gid 1000 unraid && \
    useradd --system --uid 1000 --gid unraid --create-home unraid

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

# Install the project's runtime dependencies only. Splitting dep install
# from source copy keeps the dep layer cached across code changes.
COPY pyproject.toml uv.lock README.md LICENSE /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --no-install-project

# Now copy the source and install the project itself.
COPY src /app/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen

USER unraid

# Stdio transport is the default. Override with `docker run ... unraid-mcp --check-config`
# to run the preflight instead.
ENTRYPOINT ["unraid-mcp"]
