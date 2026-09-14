# Architecture

## Hermes / NemoClaw integration (decided)

The end-to-end workflow is exposed to Hermes as **one agent, one tool call** —
not a team of separate Hermes-native agent identities, and not a scheduled/
background process. A user (the service company) asks Hermes to find and
qualify tenders; Hermes makes a single call into a NAT-registered function,
`find_and_qualify_tenders(company_profile)`, and gets back a ranked list of
`QualificationBriefing`s in that one response. Everything below the tool
boundary — discovery, ingestion, enrichment, eligibility, scoring, briefing —
runs synchronously inside that one call, orchestrated by `pipeline.py`, not as
independent Hermes agents handing off to each other.

This is deliberately **on-demand only**, not continuous monitoring: no
scheduler, no polling loop, no corrigenda re-check. That's a scope cut from
`docs/PRD.md` §7's "weekly digest" journey and §9's corrigenda-detection
success metric — both assume standing background monitoring, which is out of
scope for this workflow pass. See `docs/PRD.md` for the sections that need
updating to match; not edited here.

**Still open and blocking:** for Hermes to call `find_and_qualify_tenders` as
a real tool at all, `configs/tender_assistant_mcp.yml`'s `nat mcp` server
needs to be a Streamable HTTPS endpoint on a routable address — NemoClaw
will not register a loopback-bound or stdio server (see "Orchestration"
below). This is the one piece of infrastructure that has to land before any
of the workflow below is reachable from Hermes; everything else can be built
and tested via `python -m src.pipeline` / `nat run` in the meantime.

## Pipeline

0. **Discovery Agent**
   - Input: `CompanyProfile` (CPV/BKP codes, cantons, keywords).
   - Calls simap.ch's public, unauthenticated, read-only API **directly over
     HTTPS from pipeline code** — not via `@digilac/simap-mcp` or any MCP
     registration. This sidesteps NemoClaw's stdio-MCP restriction entirely,
     the same way `enrichment.py` (below) calls Tavily directly rather than
     through a registered MCP tool.
   - Output: a ranked list of candidate tenders. The top-N feed into
     ingestion below.
   - `integrations/simap/` (the stdio `@digilac/simap-mcp` wrapper) is
     retired in favor of this approach — see its README for why the stdio
     path was a dead end, not just untested.
   - Owner: Track A.

1. **Ingestion & Extraction Agent**
   - Input: a tender's document set (notice, cahier des charges, annexes), any
     of FR/DE/IT.
   - Output: `ExtractedTenderData` — deadlines, eligibility criteria, award
     criteria + weights, mandatory documents to submit. Every field carries a
     `Citation` (document name + page/section).
   - Owner: Track A.

2. **Enrichment Agent (Tavily)**
   - Input: `ExtractedTenderData` (buyer name, sector, unclear terminology
     surfaced during extraction).
   - Output: gap-filling context (buyer background, terminology, referenced
     registries/certifications) tagged as `external_context` — never merged
     into or treated as a grounded requirement.
   - This is `tender_search.py`, repurposed: it already makes direct Tavily
     calls (no MCP registration, matching the Discovery Agent's approach
     above); its former job — Tavily search restricted to simap.ch as a
     discovery substitute — is superseded by the real Discovery Agent (step
     0), so the module's role shifts from "find tenders" to "fill gaps in a
     tender already found." Plan to rename to `enrichment.py` when this
     lands.
   - Owner: Track A.

3. **Eligibility Gate Agent**
   - Input: `ExtractedTenderData.eligibility_criteria` + `CompanyProfile`.
   - Output: `list[EligibilityResult]` — deterministic pass/fail/unknown per
     criterion, each with a justification.
   - Intentionally deterministic/rule-based, not left to model judgment — a
     missed eligibility criterion disqualifies the bid outright, so this step
     should not be subject to probabilistic drift.
   - Owner: Track B.

4. **Fit Scoring Agent**
   - Only runs if the eligibility gate passes all mandatory criteria.
   - Input: `ExtractedTenderData.award_criteria` + `CompanyProfile`.
   - Output: `list[AwardCriterionScore]` — a 0–100 fit score per award
     criterion plus its weighted contribution.
   - Owner: Track B.

5. **Briefing Generation Agent**
   - Input: tender data, eligibility results, gate outcome, award scores.
   - Output: `QualificationBriefing` — summary, deadlines, eligibility status
     per criterion, award criteria breakdown, risk flags, go/no-go
     recommendation + justification.
   - Owner: Track C.

6. **(Deferred) Monitoring Agent** — detects corrigenda/updates to a tender
   already under review, diffs against the previously extracted data, and
   re-triggers the pipeline on material changes. Explicitly out of scope
   under the on-demand-only workflow decided above, not just "not yet built"
   — there's no standing job for it to hook into until monitoring is picked
   back up. Would also need `get_publication_history`, which — like
   discovery — should be called directly over HTTPS from pipeline code
   rather than via MCP registration when this is revisited.

## Data contracts

All inter-agent data crosses through the Pydantic models in `src/schemas/`:
`common.py` (`Citation`, `Language`), `tender.py` (`ExtractedTenderData` and
its parts), `company.py` (`CompanyProfile`), `briefing.py`
(`QualificationBriefing` and its parts). Build against these interfaces so all
three tracks can proceed in parallel without blocking on each other's agent
implementation.

## Grounding / citations

Every fact extracted from a tender document — a deadline, an eligibility
criterion, an award criterion and its weight, a mandatory document — must
carry a `Citation` (document name, and page and/or section where available).
This is a hard requirement: a bidder acting on a hallucinated deadline or
requirement is the core failure mode this system exists to prevent. The
ingestion agent attaches citations at extraction time; nothing downstream
should assert a fact without one.

## Orchestration: NeMo Agent Toolkit

The brief asks for the NVIDIA NeMo Agent Toolkit "where practical," falling
back to a simple custom orchestrator if setup friction is too high for
hackathon time.

**Decision:** adopted. `src/pipeline.py` still wires the four agents together
with plain Python function calls (`run_pipeline`) — that stays the core and
what the test suite calls directly — but the same file now also registers
each agent, plus the end-to-end pipeline, as NeMo Agent Toolkit (`nat`)
functions (`@register_function` from `nat.cli.register_workflow`). This was
possible as a `pipeline.py`-only change exactly because the three tracks'
interfaces are the framework-agnostic Pydantic schemas in `src/schemas/` —
nothing in `src/agents/*.py` had to change.

Two workflow configs live in `configs/`:

- `configs/tender_assistant.yml` — CLI: `nat run --config_file
  configs/tender_assistant.yml --input '...'`, equivalent to
  `python -m src.pipeline`.
- `configs/tender_assistant_mcp.yml` — serves the same workflow as an MCP
  server (`nat mcp --config_file ...`), intended so the NemoClaw-managed
  Hermes sandbox this environment already runs as (`tender-assistant`, see
  `~/.nemoclaw/sandboxes.json`) can call the pipeline as a tool. **Correction:**
  NemoClaw only registers *authenticated Streamable HTTPS* MCP endpoints
  (`~/.nemoclaw/source/docs/deployment/set-up-mcp-bridge.mdx`, and
  `.../manage-sandboxes/add-mcp-server.mdx`: "Stdio-only MCP servers are not
  supported... Direct 127.0.0.1... remain rejected") — running `nat mcp`
  bound to loopback alone isn't sufficient for Hermes to reach it; it needs a
  real HTTPS reverse proxy on a routable, non-loopback address first (the
  `~/hpe-nvidia-hackathon/hermes-ingress/nginx.conf` pattern already in this
  workspace, fronting the Hermes dashboard itself, is the precedent — whether
  this environment's Launchpad allocation can front a *second* service the
  same way is unconfirmed and needs checking before investing more time here).
  This is a separate, still-open problem from live tender discovery below,
  which sidesteps it entirely by using Tavily's own natively-supported,
  already-HTTPS integration instead of our own MCP server.

This doesn't block Track A/B/C from implementing agent logic against
`src/schemas/` exactly as before — `nat run`/`nat mcp` are additional ways to
invoke the same code, not a replacement for `python -m src.pipeline`.

## Tavily usage: from discovery to enrichment

`src/agents/tender_search.py` originally found candidate tenders in the first
place — `docs/CHALLENGE.md`'s "Identify relevant tenders" step — by calling
Tavily's search API directly (shallow pass restricted to simap.ch, then a
deep pass scoped to the company's capabilities), producing cited
`TenderLead`s (`src/schemas/discovery.py`). Wired into NAT as
`tender_live_search` (`configs/tender_live_search.yml`).

**Superseded by the Discovery Agent** (Pipeline step 0 above): real tender
discovery now calls simap's own API directly instead of using Tavily as a
stand-in. `tender_search.py`'s working direct-Tavily-call code is repurposed
into the **Enrichment Agent** (Pipeline step 2) instead of being discarded —
same calling pattern, different job (gap-filling context on a tender already
found, not finding the tender). Rename to `enrichment.py` when this lands.
Tavily is also NemoClaw/Hermes's own native web-search provider for this
project's sandbox — see `docs/aiq-blueprint.md` "Hermes's native Tavily web
search" for that side and how it relates to a separately-cloned AI-Q Research
Agent Blueprint that's no longer on this path but is kept around for possible
future deep-research use.

## Input format and simap access (decided)

Earlier notes here said simap.ch "has no official public API" and treated
live discovery as a stretch goal, with `data/sample_tenders/` local PDFs as
the only demo input and `integrations/simap/` (a third-party stdio MCP
server) as a stalled attempt at more. That's superseded: simap.ch does expose
a public, unauthenticated, read-only API (`docs/PRD.md` §2/§4), and the
Discovery and (future) Monitoring agents call it **directly over HTTPS from
pipeline code** — the same direct-call pattern already proven for Tavily —
rather than through any MCP registration.

`integrations/simap/` (the `@digilac/simap-mcp` stdio wrapper) is retired,
not fixed: it was blocked on NemoClaw's stdio-MCP restriction, and calling
simap's API directly sidesteps that restriction entirely rather than working
around it. Local PDFs in `data/sample_tenders/` remain useful for testing the
ingestion/eligibility/scoring/briefing stages in isolation, independent of
live discovery.
