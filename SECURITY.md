# Security Policy

## Reporting a Vulnerability

Please report security vulnerabilities privately via GitHub's
[private vulnerability reporting](https://github.com/millsmillsymills/unraid-mcp/security/advisories/new)
feature. Do **not** open a public issue.

You should receive an acknowledgement within 7 days. After triage, a fix
timeline and disclosure date will be coordinated with you.

## Scope

In scope:

- Code in `src/unraid_mcp/`
- The repository's `Dockerfile` (and any image you build from it)
- CI workflows in `.github/workflows/`

Out of scope (report upstream instead):

- Vulnerabilities in the Unraid GraphQL API itself — report to Lime Technology.
- Vulnerabilities in dependencies — report to the upstream project.

## Operational guidance

`unraid-mcp` is a privileged client: it holds an API key that can read
system state and (in `readwrite` mode) start/stop containers, VMs, and
the array. To minimise blast radius:

- Run in `UNRAID_MODE=readonly` unless you specifically need writes.
- Treat the value of `UNRAID_API_KEY` as a credential. Don't commit it,
  don't paste it into shell history files or AI assistant transcripts,
  and rotate it via the Unraid WebGUI if it was ever exposed.
- Leave `UNRAID_VERIFY_SSL` at its default of `true`. Override to `false`
  only when your Unraid server uses a self-signed cert AND you accept the
  MITM risk on that network segment — disabling verification lets any
  attacker on the network path capture the `x-api-key` header and any
  in-flight credentials.
