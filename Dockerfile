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

ARG PYTHON_IMAGE=python:3.13-slim@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1
FROM ${PYTHON_IMAGE} AS base

# uv provides fast, reproducible dep resolution and pulls the pinned
# versions from uv.lock. Pin both images by digest; dependency updates
# must pass the container build and trust checks before integration.
COPY --from=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 /uv /uvx /usr/local/bin/

# The base interpreter has its own pip trust bundle, separate from uv
# and the application environment. Bootstrap it through patched uv.
RUN uv pip install --system --no-cache "pip==26.3"

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
