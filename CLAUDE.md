# Agent Instructions

## Project Overview

Agentic system that ingests Swiss public tender documents (simap.ch), extracts their
requirements, and produces a structured qualification briefing to support a bidder's
go/no-go decision — every extracted fact traceable to its source document. Built for the
HPE & NVIDIA Agentic AI Hackathon for Enterprises (Swiss AI Weeks) by a 3-person team.

See [`docs/CHALLENGE.md`](docs/CHALLENGE.md) for the official brief, [`README.md`](README.md)
for the pipeline overview, and [`docs/architecture.md`](docs/architecture.md) for the full
design and its key decisions.

Status: skeleton stage. Schemas are defined; the four core pipeline agent modules are
stubbed with `NotImplementedError` and `# TODO(track-x)` markers; orchestration wiring
(both plain Python and NeMo Agent Toolkit) exists and works end-to-end once agent logic
lands. One exception: `src/agents/tender_search.py` (live discovery via Tavily) is real,
working code, not a stub — see `docs/aiq-blueprint.md`.

## Architecture

| Path | Purpose |
|------|---------|
| `src/schemas/` | Pydantic contracts shared between all agents — read this first |
| `src/agents/ingestion.py` | Track A — PDF parsing, extraction, citations, FR/DE/IT |
| `src/agents/eligibility_gate.py` | Track B — deterministic pass/fail eligibility check |
| `src/agents/fit_scoring.py` | Track B — weighted award-criteria scoring |
| `src/agents/briefing.py` | Track C — final structured briefing + go/no-go |
| `src/agents/tender_search.py` | Track A (stretch) — **implemented**, not a stub: live tender discovery via Tavily search |
| `src/pipeline.py` | Track C — plain-Python orchestration **and** NAT function registration (the only file NAT adoption changed) |
| `configs/` | NeMo Agent Toolkit (`nat`) workflow YAML — CLI, MCP-server, and live-search variants |
| `integrations/simap/` | simap.ch MCP server groundwork (stretch goal, architecturally broken — see its README before building on it) |
| `data/sample_tenders/` | Local PDF inputs for the demo (gitignored, see its README) |
| `tests/` | Mirrors `src/`, one test module per agent + schema tests |
| `docs/` | `architecture.md` (pipeline design), `aiq-blueprint.md` (Tavily web search + Hermes native integration + the AI-Q Blueprint's status), `CHALLENGE.md` (hackathon brief) |

## Quick Reference

| Task | Command |
|------|---------|
| One-command dev setup | `./scripts/setup.sh` |
| Run tests | `pytest` |
| Lint | `ruff check .` |
| Format | `ruff format .` |
| Run all pre-commit hooks | `pre-commit run --all-files` |
| Run pipeline directly | `python -m src.pipeline <tender_folder> <company_profile>` |
| Run pipeline via NAT | `nat run --config_file configs/tender_assistant.yml --input '...'` |
| Serve pipeline as MCP (for Hermes) | `nat mcp --config_file configs/tender_assistant_mcp.yml` |
| Live tender discovery (needs `TAVILY_API_KEY` in `.env`) | `nat run --config_file configs/tender_live_search.yml --input '...'` |
| List registered NAT functions | `nat info components -t function` |

## Key Architecture Decisions

- **NeMo Agent Toolkit adoption** — `src/pipeline.py` registers each agent (and the
  end-to-end pipeline) as a `nat` function via `@register_function`; `configs/` holds
  the workflow YAML. This was deliberately deferred until agent logic existed enough to
  orchestrate, and landed as a `pipeline.py`-only change because the schemas in
  `src/schemas/` are framework-agnostic. See `docs/architecture.md` "Orchestration" for
  the full rationale — don't re-litigate this decision without reading it first.
- **Deterministic eligibility gate** — `eligibility_gate.py` must stay rule-based, not
  left to model judgment: a missed mandatory criterion disqualifies a bid outright, so
  it can't be subject to probabilistic drift. `fit_scoring.py` (weighted, LLM-judgment
  territory) only runs after the gate passes.
- **Hard citation requirement** — every extracted fact (deadline, criterion, weight,
  mandatory document) must carry a `Citation` (`src/schemas/common.py`) back to its
  source document. This is the core failure mode the system exists to prevent — never
  add a field to `ExtractedTenderData` or its children without a citation, and never
  assert a fact in `briefing.py` that isn't grounded in an upstream citation.
- **FR/DE/IT input** — tender documents may be in any of the three; `ingestion.py`
  must handle all three, not just the language you're testing with.
- **Live tender discovery calls Tavily directly**, not the AI-Q Blueprint — a `~/aiq-blueprint`
  checkout exists (cloned and set up in an earlier iteration of this work) but is no longer on
  `tender_search.py`'s path; see `docs/aiq-blueprint.md` for the full history and why it's kept
  around. Don't route new work through it without reading that doc first — Tavily direct is the
  current, simpler, working path, and also what Hermes itself uses natively (same doc).

## Code Style

- Pydantic-first: shared contracts live in `src/schemas/`, not ad hoc dicts.
- `ruff` — line length 100, target `py311` (see `pyproject.toml`); enforced by
  `pre-commit` locally and CI on every PR.
- Existing `# TODO(track-x)` convention in stub files — keep using it as agent logic
  lands, don't delete a TODO without implementing what it names.
- Docstrings: short, purpose-first (see existing `src/agents/*.py` for the house style)
  — no restating the signature, no narrating implementation steps.

## Team split

- **Track A — Ingestion & extraction**: `src/agents/ingestion.py`
- **Track B — Eligibility & scoring**: `src/agents/eligibility_gate.py`, `src/agents/fit_scoring.py`
- **Track C — Briefing & orchestration**: `src/agents/briefing.py`, `src/pipeline.py`, CLI/demo

All three tracks build against `src/schemas/` — implement against those interfaces and
you're not blocked on each other's progress.

## Working with This Repo

- Read [`CONTRIBUTING.md`](CONTRIBUTING.md) first: feature branch off `main`, small
  focused commits, PR + one teammate review, never push straight to `main` once there's
  shared code, `.env` never committed.
- Run `./scripts/setup.sh` before your first change — it installs the `pre-commit`
  hooks that CI also enforces, so lint/format issues surface before you open a PR, not
  during review.
- This environment runs inside a NemoClaw-managed Hermes sandbox named
  `tender-assistant` (see `~/.nemoclaw/sandboxes.json` if you need to confirm) — that's
  the coding-agent harness for building this repo, and separately the intended runtime
  for the finished pipeline via `nat mcp` (see Quick Reference above). Don't build a
  custom NemoClaw sandbox image or blueprint manifest for this project — that pattern
  belongs to NemoClaw's own repo, not an application repo; exposing an MCP tool the
  existing sandbox calls is the right-sized integration here. **But note:** NemoClaw only
  registers authenticated Streamable HTTPS MCP endpoints
  (`~/.nemoclaw/source/docs/deployment/set-up-mcp-bridge.mdx`) — no stdio, no loopback.
  `nat mcp` alone isn't enough for Hermes to call *this pipeline*; see
  `docs/architecture.md` "Orchestration" for that gap. Web search is a separate,
  already-solved integration point — NemoClaw has native Tavily support for Hermes (not
  generic MCP); see `docs/aiq-blueprint.md` "Hermes's native Tavily web search" — not yet
  enabled for this sandbox, needs a real key and sandbox recreation.

## Gotchas

- `integrations/simap/` (live simap.ch tender search via MCP) is present but
  architecturally broken, not just flaky — it's a stdio MCP server, and NemoClaw
  doesn't support those at all (see above). See its README before relying on it or
  "fixing" it with network-policy changes, which won't help.
- `NVIDIA_API_KEY` and `.env` (copy from `.env.example`) are required before running
  `nat` — it won't start without them.
- `nvidia-nat`'s Python import namespace is `nat`, not `aiq`, despite the package having
  been distributed as `aiqtoolkit` in the past — don't guess the old import path.
- `TAVILY_API_KEY` (this repo's own `.env`) is required before `tender_search.py`/
  `tender_live_search` will work — it raises a clear `RuntimeError` if missing rather than
  silently no-op'ing.
- `~/aiq-blueprint` still exists (isolated `uv` venv, its own `deploy/.env`) but nothing in
  this repo calls it anymore — see `docs/aiq-blueprint.md` before reviving that path.
