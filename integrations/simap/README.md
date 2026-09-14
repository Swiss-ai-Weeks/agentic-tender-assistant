# simap.ch MCP integration (stretch goal)

`CHALLENGE.md` notes simap.ch has no public API. [`@digilac/simap-mcp`](https://www.npmjs.com/package/@digilac/simap-mcp)
is a third-party MCP server that claims to expose one anyway (`list_cantons`,
`search_tenders`, and more — 14 tools total), which would let Track A's
ingestion agent discover live tenders instead of only reading local PDFs from
`data/sample_tenders/`.

- `package.json` — the npm dependency.
- `policy.yaml` — the NemoClaw network policy needed to run this MCP server
  inside the Hermes sandbox: read-only `GET` to `www.simap.ch/api/**` only.

## Status: architecturally broken, not just flaky

Two test runs against the "tender-assistant" Hermes sandbox both failed to
reach the tool (timeouts, then the tool not appearing in the registry at
all). That looked like a network/connectivity problem at the time. It isn't:

**`@digilac/simap-mcp` is a stdio MCP server** (a local npm process talking
MCP over stdin/stdout), and per NemoClaw's own documented architecture
(`~/.nemoclaw/source/docs/deployment/set-up-mcp-bridge.mdx` and
`~/.nemoclaw/source/docs/manage-sandboxes/add-mcp-server.mdx`, read directly
while building the AI-Q Blueprint integration — see `docs/aiq-blueprint.md`):

> "NemoClaw accepts Streamable HTTP MCP endpoints only. It does not launch an
> MCP server, stdio adapter, bridge, credential proxy, data-plane relay, or
> listener on the host." ... "Stdio-only MCP servers are not supported.
> NemoClaw does not start, wrap, or translate them."

No amount of network-policy tuning fixes this — NemoClaw was never going to
run this package at all, stdio MCP servers aren't in scope for it, full stop.
The `policy.yaml` egress rule here may still be necessary for a *fixed*
version, but it was never sufficient.

## The actual fix path, if picked up

To work with NemoClaw, a SIMAP integration needs to be a real **Streamable
HTTPS MCP endpoint** — a server bound to a routable address with a valid TLS
certificate, not a local stdio process. `docs/aiq-blueprint.md` documents the
same requirement being worked through for the AI-Q Blueprint's own MCP server
(reusing `~/hpe-nvidia-hackathon/hermes-ingress/nginx.conf`'s pattern for
HTTPS-fronting a local service via the Launchpad-issued hostname already used
for the Hermes dashboard) — the same approach would apply here: either get
`@digilac/simap-mcp` (or a replacement) running behind such a proxy, or drop
it in favor of a plain HTTPS API if simap.ch ever exposes one.

`src/agents/ingestion.py`'s TODO note points here and at
`src/agents/tender_search.py` (the AI-Q Blueprint-backed live discovery path
that *is* working, as of this integration, for general web search — just not
simap.ch-specific structured data).
