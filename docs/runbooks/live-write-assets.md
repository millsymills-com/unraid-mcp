# Runbook: live-write test assets (one-time tower setup)

The live mutating suite (`tests/live_write/`) toggles state on throwaway assets
named with the `mcptest-` prefix and never deletes them. Discovery is by prefix:
any asset whose name starts with `mcptest` is fair game, anything else is
refused (`tests/live_write/_gates.py`). Each fixture skips cleanly when its
asset is absent, so the suite is green-by-skip until you provision these.

This runbook provisions all three asset classes the suite exercises:

| Asset | Name | Tests | Created by |
|-------|------|-------|------------|
| Docker container | `mcptest-nginx` | start / stop / pause / unpause / restart | you (once) |
| Virtual machine | `mcptest-vm` | start / stop / pause / resume / reboot | you (once) |
| Notifications | `mcptest-*` title | archive / delete / archive_all | seed per run (SSH) |

Parity tests need no asset — they drive the array's own parity check.

## Prerequisites

- `.env` at the repo root with a working `UNRAID_API_KEY` and `UNRAID_HOST`
  (pin to the LAN IP, e.g. `UNRAID_HOST=192.168.1.115`, to bypass mDNS).
  Confirm with `uv run unraid-mcp --check-schema`.
- SSH access to the tower as `root` (for the notification seed step).
- Substitute your tower's IP for `192.168.1.115` below.

## 1. Docker container — `mcptest-nginx`

A plain `docker run` container is discoverable by the API; no Unraid template
is required. Over SSH:

```bash
ssh root@192.168.1.115 'docker run -d --name mcptest-nginx --restart=no nginx:alpine'
```

Or via the WebGUI: **Docker → Add Container**, Name `mcptest-nginx`, Repository
`nginx:alpine`, network `bridge`, **Apply**, then **Start**.

Verify it is visible to the MCP layer:

```bash
set -a; . ./.env; set +a
uv run pytest -m integration -o addopts="" -q -k list_containers
```

## 2. Virtual machine — `mcptest-vm`

The VM tests only toggle libvirt domain state — the guest never needs to boot a
real OS — so a minimal definition is enough. Via the WebGUI:

**VMs → Add VM** → any Linux template → Name `mcptest-vm`, 1 vCPU, 512 MB RAM,
a small (or no) vDisk, no install media. **Create**. Leave it stopped; the
`start_vm` test brings it up.

> If the VMs tab is absent, enable the VM manager first:
> **Settings → VM Manager → Enable VMs = Yes → Apply**.

Verify discovery:

```bash
set -a; . ./.env; set +a
uv run pytest -m integration -o addopts="" -q -k list_vms
```

## 3. Notification seeds (per run)

The notification tests archive/delete a `mcptest-*`-titled notification, so each
asset is consumed once. Seed two fresh notifications immediately before a run
using Unraid's `notify` helper over SSH:

```bash
ssh root@192.168.1.115 \
  '/usr/local/emhttp/webGui/scripts/notify -e "mcptest-archive" -s "mcptest" -d "live-write seed" -i normal; \
   /usr/local/emhttp/webGui/scripts/notify -e "mcptest-delete" -s "mcptest" -d "live-write seed" -i normal'
```

`archive_all` only runs when **every** active notification is `mcptest-*`; on a
tower with real alerts it skips by design — that is expected, not a failure.

## 4. Run the live-write suite

```bash
set -a; . ./.env; set +a
UNRAID_ALLOW_LIVE_WRITES=1 uv run pytest -m live_write -o addopts="" -v
```

A 3-second abort banner prints before any mutation. With all assets present the
docker (3) and VM (3) tests run instead of skipping, the seeded notification
tests pass, and parity runs as before.

## 5. Teardown

Tests never delete these assets. Remove them when done:

```bash
ssh root@192.168.1.115 'docker rm -f mcptest-nginx'
```

Delete `mcptest-vm` from the VMs tab. A session-end orphan scan warns on stderr
about any leftover `mcptest-*` notifications — archive or delete those from the
Notifications panel.
