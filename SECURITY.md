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
- The published `unraid-mcp` PyPI package
- The published Docker image
- CI / release workflows in `.github/workflows/`

Out of scope (report upstream instead):

- Vulnerabilities in the Unraid GraphQL API itself — report to Lime Technology.
- Vulnerabilities in dependencies — report to the upstream project.

## Operational guidance

`unraid-mcp` is a privileged client: it holds an API key that can read
system state and (in `readwrite` mode) start/stop containers, VMs, the
array, and create users. To minimise blast radius:

- Run in `UNRAID_MODE=readonly` unless you specifically need writes.
- Keep `UNRAID_ALLOW_USER_MUTATIONS=false` unless you need account
  management — even in `readwrite` mode the create/delete user tools
  stay hidden behind this secondary gate.
- Treat the value of `UNRAID_API_KEY` as a credential. Don't commit it,
  don't paste it into shell history files or AI assistant transcripts,
  and rotate it via the Unraid WebGUI if it was ever exposed.
- Prefer `password_env_var` over the inline `password` argument when
  calling `unraid_create_user` so secrets stay out of MCP transcripts.
- Set `UNRAID_VERIFY_SSL=true` whenever your Unraid server has a valid
  TLS cert. The default is `false` only because LAN appliances commonly
  ship with self-signed certs.
