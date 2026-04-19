#!/usr/bin/env bash
# Smoke-test the built wheel end-to-end:
#   1. `uv build` produces sdist + wheel
#   2. Install the wheel into a clean venv
#   3. `unraid-mcp --version` runs
#   4. `unraid-mcp --check-config` runs to completion (exit 0/1/2 all OK;
#      we only fail on crashes like ImportError / AttributeError)
#   5. `unraid-mcp --help` lists the expected flags
#
# Exit non-zero on any structural failure. Safe to run without an Unraid
# host — no validation succeeds in this environment, but the CLI must not
# crash.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SMOKE_DIR="$(mktemp -d -t unraid-mcp-smoke.XXXXXX)"
trap 'rm -rf "$SMOKE_DIR"' EXIT

cd "$REPO_ROOT"

echo "==> uv build"
rm -rf dist
uv build

SDIST=$(ls dist/*.tar.gz | head -1)
WHEEL=$(ls dist/*.whl | head -1)
test -f "$SDIST" || { echo "no sdist produced"; exit 1; }
test -f "$WHEEL" || { echo "no wheel produced"; exit 1; }
echo "    built: $(basename "$SDIST"), $(basename "$WHEEL")"

echo "==> py.typed marker present in wheel"
# Capture the listing first — piping directly into `grep -q` combined with
# `set -o pipefail` fails (141 / SIGPIPE) because grep closes stdin before
# unzip finishes writing.
WHEEL_CONTENTS=$(unzip -l "$WHEEL")
if ! echo "$WHEEL_CONTENTS" | grep -q "unraid_mcp/py.typed"; then
    echo "py.typed missing from wheel"
    exit 1
fi

echo "==> fresh venv install"
python3 -m venv "$SMOKE_DIR/venv"
"$SMOKE_DIR/venv/bin/pip" install --quiet --upgrade pip
"$SMOKE_DIR/venv/bin/pip" install --quiet "$WHEEL"
UNRAID_MCP="$SMOKE_DIR/venv/bin/unraid-mcp"
test -x "$UNRAID_MCP" || { echo "unraid-mcp entry point not installed"; exit 1; }

echo "==> --version"
VERSION_OUT=$("$UNRAID_MCP" --version)
echo "    $VERSION_OUT"
case "$VERSION_OUT" in
    "unraid-mcp "*) ;;
    *) echo "unexpected --version output: $VERSION_OUT"; exit 1 ;;
esac

echo "==> --help"
HELP_OUT=$("$UNRAID_MCP" --help)
for flag in "--version" "--check-config"; do
    if ! echo "$HELP_OUT" | grep -q -- "$flag"; then
        echo "--help is missing $flag"
        exit 1
    fi
done

echo "==> --check-config (no API key → exit 1, non-crashing)"
set +e
env -u UNRAID_API_KEY "$UNRAID_MCP" --check-config >"$SMOKE_DIR/check.out" 2>&1
EXIT_CODE=$?
set -e
if [[ "$EXIT_CODE" -ne 1 ]]; then
    echo "expected exit 1, got $EXIT_CODE"
    cat "$SMOKE_DIR/check.out"
    exit 1
fi
if ! grep -q "No API key configured" "$SMOKE_DIR/check.out"; then
    echo "--check-config did not print the expected no-key message"
    cat "$SMOKE_DIR/check.out"
    exit 1
fi

echo ""
echo "smoke passed: wheel builds, installs, CLI runs."
