# Tavily web search, the AI-Q Blueprint, and Hermes

`src/agents/tender_search.py` (live tender discovery, see `docs/architecture.md` "Live tender
discovery") calls **Tavily directly** — the same web-search provider NemoClaw/Hermes uses
natively for this project's own sandbox. This page covers that native Hermes integration, how
this repo's own pipeline uses Tavily, and the separately-cloned AI-Q Research Agent Blueprint
that's still available for deeper research if the team wants it later.

## Hermes's native Tavily web search

NemoClaw has first-class, built-in Tavily support for Hermes sandboxes — this is **not** a
generic MCP server registration; it's a dedicated onboarding-time setting. Verified directly
against `~/.nemoclaw/source/docs/get-started/quickstart-hermes.mdx` and
`~/.nemoclaw/source/docs/network-policy/integration-policy-examples.mdx`:

- A network policy preset, `tavily.yaml`, ships with NemoClaw and permits exactly `POST
  /search` and `POST /extract` to `api.tavily.com` — nothing else.
- Hermes sends its Tavily API key as an OpenShell resolver placeholder in the request's JSON
  `api_key` field ("request-body credential rewriting"); OpenShell replaces it with the real
  key at egress, so the raw key is never written into sandbox configuration.
- Enabling it writes `web.backend: tavily` into the Hermes configuration.

**This project's `tender-assistant` sandbox does not have it enabled yet**
(`~/.nemoclaw/sandboxes.json` shows `"webSearchEnabled": false, "webSearchProvider": null`).
Enabling it needs a real `TAVILY_API_KEY` and **requires sandbox recreation** — per the docs,
"Changing or disabling Tavily requires sandbox recreation because the backend, credential
attachment, and policy selection are startup-profile inputs." That's disruptive to whatever's
running in that sandbox right now, so it wasn't done unilaterally as part of this change. Once
a real key is available:

```bash
nemoclaw tender-assistant policy add tavily --dry-run   # preview the network policy change
nemoclaw tender-assistant policy add tavily --yes
# Then re-run onboarding with Tavily selected and accept recreation:
NEMOCLAW_WEB_SEARCH_PROVIDER=tavily TAVILY_API_KEY=<key> nemoclaw onboard --name tender-assistant --recreate-sandbox --agent hermes
```

Both commands verified against the real installed `nemoclaw` CLI (`nemoclaw tender-assistant
policy add --help`, `nemoclaw onboard --help`) — the flags shown above exist and match this
shape. Not run end-to-end: it needs a real `TAVILY_API_KEY` and explicit go-ahead before
recreating a sandbox other things may be using.

## How `agentic-tender-assistant` calls Tavily

`src/agents/tender_search.py` → `discover_tenders(query, company)`, two synchronous calls to
`POST https://api.tavily.com/search` (no separate backend process, no polling):
1. Shallow pass — `search_depth: basic`, the raw query, restricted to `simap.ch`/`www.simap.ch`.
2. Deep pass — `search_depth: advanced`, the query augmented with the company's `capabilities`.

Each real Tavily result becomes one `TenderLead` (`src/schemas/discovery.py`), citation pointing
at that result's actual URL and content snippet — a genuine per-fact citation, not a summary.
Wired into NAT as `tender_live_search` (`src/pipeline.py`, `configs/tender_live_search.yml`).

Needs `TAVILY_API_KEY` in this repo's own `.env` (`.env.example`) — the same key used for
Hermes's native integration above, but configured independently; this repo's pipeline and the
Hermes sandbox are two separate processes/credentials even when pointed at the same provider.

## The AI-Q Research Agent Blueprint (still available, no longer on the search path)

An earlier iteration of `tender_search.py` called a real, separately-running copy of the
[NVIDIA AI-Q Research Agent Blueprint](https://github.com/NVIDIA-AI-Blueprints/aiq), cloned to
`~/aiq-blueprint` and set up successfully (`./scripts/setup.sh` completed in this session). That
integration is no longer what `tender_search.py` uses — plain Tavily calls are simpler, need no
separate process, and match what Hermes itself does natively (above). The clone is left in place
because the blueprint's multi-step deep-research agent (intent classification, clarification,
citation-verified synthesis across many searches) is genuinely more capable than two raw Tavily
calls, and may be worth revisiting for a "full qualification briefing from an open-ended
question" feature later — just not for the current shallow/deep discovery step.

If picked back up:

```bash
cd ~/aiq-blueprint
source .venv/bin/activate
# Edit deploy/.env: set NVIDIA_API_KEY and TAVILY_API_KEY
nat serve --config_file configs/config_cli_default.yml --port 8000
```

Why it's a separate checkout, not a dependency of this repo: its core package (`aiq-agent`,
`src/aiq_agent/`) pins an exact `nvidia-nat==1.8.0` (verified directly in its `pyproject.toml` —
re-check there, this number moves with blueprint releases), while this repo depends on
`nvidia-nat[mcp]>=1.9,<2` — an exact pin and a floor two majors apart can't share one `pip`
resolution. `~/aiq-blueprint/skills/aiq-research/scripts/aiq.py` is NVIDIA's own reference REST
client for it (stdlib-only), useful for manual testing if this gets revisited.

Its own MCP server (`mcp/` subproject, Postgres-backed) hits the same NemoClaw
Streamable-HTTPS-only constraint described above for any *other* MCP server — not relevant now
that Tavily itself is used directly and natively supported by Hermes.

## Keeping the clone in sync

`~/aiq-blueprint` is an independent upstream checkout — `git -C ~/aiq-blueprint pull` to update
it, same as any other clone, if it gets used again.
