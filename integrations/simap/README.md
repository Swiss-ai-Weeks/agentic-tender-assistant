# SIMAP MCP for Hermes

Verified in the workshop on 14 September 2026: 14 tools discovered; direct and real in-agent calls returned 26 cantons and software tenders with source links. Missing proxy/CA subprocess settings caused earlier connectivity failures. Application ingestion integration remains separate work.

## Installation

Run `npm ci --ignore-scripts` in this directory in an isolated install location. The lockfile comes from the deployed host tree, with the direct dependency pinned to its resolved 1.4.0. Validate in a separate environment before replacing the running installation. Transfer the installed directory to `/sandbox/.hermes/mcp/simap` using the supported upload flow (`nemohermes tender-assistant upload --help`). Keep dependencies out of Git. The Node runtime must support `--use-env-proxy`.

From the repository root, deliberately apply the preset with `nemohermes tender-assistant policy add --from-file integrations/simap/policy.yaml --yes`. It permits only Node HTTPS GET requests to `www.simap.ch/api/**`. Public discovery requires no account key; protected documents are not covered by these tests.

## Registration

Use native Hermes stdio registration (`hermes mcp add --help`); NemoClaw 0.0.123 managed MCP registration supports HTTP servers. Merge `hermes-config.example.yaml` into the intended profile without replacing unrelated settings. The workshop registered both base and dashboard profiles; paths are in [the runbook](../../docs/NEMOHERMES_SETUP.md). Verify proxy and certificate paths inside the actual sandbox namespace. Preserve TLS verification.

The example includes the recovery settings applied to the base profile: `connect_timeout: 10` and `lazy: true`. Lazy discovery uses a matching schema cache when available, otherwise it connects normally. This is not proof of the original outage cause.

## Validation

Check 14 tools in the intended profiles. Call `list_cantons` and `search_tenders(search=software)`, then repeat through a fresh Hermes chat asking for source links. Discovery alone does not prove connectivity. Keep raw session and API evidence outside Git. Preserve the application local-PDF path while adding live discovery.
