# Implementation status — Agentic Tender Assistant (NVIDIA instance)

Host: `hot-ready-ubuntu-h100-2-MrLj-gpu01`. Branch: `feat/handoff-reconcile-nvidia`.
Date: 2026-09-15. All work below was done and verified on this instance.

Re-verified end-to-end this session (fresh runs, see "Re-verification" below):
122/122 tests pass with byte-identical real DB, live lab endpoint probed with
bounded requests, UI builds, all 7 containers / GPU allocations / ports intact.

## Current product entrypoint

- API: `src/opportunity/api.py` (FastAPI loopback service).
  Run: `.venv/bin/python -m uvicorn src.opportunity.api:app --port 8090`
  (never port 8000 — Hermes/nemoclaw-vllm occupies it on GPU 0).
- UI: `ui/` (React). Build: `cd ui && npm run build`. Serve `ui/dist/`.
- Evaluate fixtures: `.venv/bin/python -m src.opportunity.evaluation`.
- Document pack CLI: `.venv/bin/python scripts/import_tender_documents.py <pack>
  --tender-id <id> --out <new-dir> [--complete-set-reviewed --reviewed-by <who>]`.
- Legacy scaffold `src/agents/` + `src/pipeline.py` remains stubbed
  (`NotImplementedError`); not the product entrypoint.

## Changes completed this session

1. **Handoff reconciled on `feat/handoff-reconcile-nvidia`** (no overwrite of
   newer work). The staged Mac handoff (`/home/nvidia/tender-handoff.4zCAWy`,
   SHA-256 manifest verified ALL-OK for every file taken) was older than this
   checkout's uncommitted backend work, and newer only in docs/UI plus three new
   files. Merged deliberately:
   - Taken from handoff (verified hashes): `src/opportunity/documents.py`,
     `tests/opportunity/test_documents.py`, `scripts/import_tender_documents.py`,
     `docs/RESUME_STATUS.md`, `README.md`, `docs/JURY_DEMO.md`, `docs/PRD.md`,
     `ui/src/main.tsx` (docs/UI corrections: 340B/two-GPU/immunity/sovereign/
     4.5h claims removed, controlled-scope labels).
   - Preserved from this checkout (newer, not in handoff): uncommitted model
     integration in `src/opportunity/nemotron.py`, truthful `/api/system` in
     `src/opportunity/api.py`, `TENDER_DB_PATH` override in
     `src/opportunity/db.py`, model wiring in `src/opportunity/simap.py`.
2. **Real optional model integration** (`src/opportunity/nemotron.py`,
   `tests/opportunity/test_nemotron.py`, 16 tests): bounded OpenAI-compatible
   HTTP candidate generation (`httpx`, configurable timeout, 256 max tokens,
   `response_format: json_object`), strict shape allowlist
   (fields/references/insurance/certifications/revenue/languages,
   operators `>=`/`contains`, numeric ranges, no extra keys), `abstain`
   handling, injection detection, disabled-by-default
   (`TENDER_LLM_ENABLED=1` + endpoint + model + per-call `use_llm=True`
   required). Wired into the real path via
   `simap.notice_opportunity(..., llm, use_llm)`; `/api/system` reports
   disabled/configured-incomplete/configured truthfully and never probes the
   network. `.env.example` documents all `TENDER_LLM_*` variables.
3. **Tender document import** (handoff code, verified here): `documents.py`
   with SHA-256 preservation, exact page/line quote citations, FR/DE/IT Unicode
   intact, EMPTY/SCANNED/ENCRYPTED/UNSUPPORTED/OVERSIZE review states, symlink
   and path-traversal rejection, file/page limits, explicit human-reviewed
   completeness flag (never inferred). `pypdf` installed in the project venv
   only and declared in `pyproject.toml` (`pypdf>=4,<7`); no other packages
   changed. 11/11 tests pass (matches handoff's `documents-local-tests.txt`).
4. **Real bidder evidence loader** (new): `src/opportunity/bidder.py` +
   `tests/opportunity/test_bidder.py` (14 tests). Explicit pack dir + manifest
   (company, rows with field/value/unit/validity/exact quote/file+line-or-page/
   SHA-256, `reviewed_by`/`reviewed_at` attestation). Only matching reviewed
   rows become `VERIFIED_INTERNAL` `Evidence` (attestation of source match, not
   issuer authenticity); everything else is a review issue → UNKNOWN, never
   PASS. Synthetic `data/demo` fixtures are never read.
5. **Acceptance coverage** (new): `tests/opportunity/test_acceptance.py`
   (5 tests) — FR/DE/IT pack → cited rules → bidder evidence → briefing:
   all-PASS→GO, missing evidence→UNKNOWN (never fabricated NO-GO),
   insufficient evidence→NO-GO with citation, v1→v2 amendment diff
   (`recompile_diff`) with the added rule evaluated, unreviewed set never GO.
6. **Docs corrected to the new reality**: README/JURY_DEMO model bullets now
   describe the implemented optional proposer (not "pending"); run ports fixed
   to 8090 with a never-8000 note.

## Re-verification (this session, 2026-09-15 ~13:30 UTC)

- Full suite `TENDER_DB_PATH=/tmp/tender-forensic.db .venv/bin/python -m
  pytest tests/` → **122 passed**, 2 pre-existing warnings. Real-DB isolation
  proven by hash: `data/evidence_provenance.db` md5 `bfdf218b...` identical
  before and after; suite writes landed in `/tmp` (835 KB fresh DB) instead.
  (One `./scripts/setup.sh` was run early in this session; `git status` before
  and after is identical — venv/hooks only, no tree or package changes.)
- Live lab endpoint (read-only, bounded, GPU 1; no server started, no
  benchmark): `GET /v1/models` → `h100-lab-nemotron-4b-fp8` (`max_model_len`
  32768). Through the repo path (`fetch_remote_candidate` +
  `compile_clause_with_guard`, `TENDER_LLM_ENABLED=1`): model output varies
  run-to-run — one call returned schema-valid `references >= 3`, another
  returned non-conforming keys. Both handled safely: non-conforming output
  rejected by `validate_remote_shape`, valid-but-unanchorable candidates
  escalated to NEEDS_REVIEW by `validate_candidate`, injection clause detected
  + reported with deterministic compile unchanged, vague clause UNSUPPORTED.
  No run fabricated PASS; the deterministic gate stayed authoritative.
- Default-off confirmed: `test_disabled_by_default_sends_no_request` mocks
  `httpx.Client` with an exploding stub — no HTTP client may be constructed
  while disabled; `status()` never probes the network.
- `cd ui && npm run build` → PASS (`tsc -b && vite build`, 2.53 s).
- Lint: under the enforced rule set (pinned pre-commit ruff v0.6.9 defaults,
  `E4,E7,E9,F`) the only findings are 4 pre-existing ones in untouched lines
  (`api.py:99` F401 from commit `4750869`, `engine.py:76` E731,
  `test_product.py` E741 ×2 — all confirmed via `git blame`, none from session
  edits). The 7 extra findings from venv ruff 0.16.7 (BLE001/S110/TRY004/
  RUF100) are outside the enforced set; the two BLE001 sites in `nemotron.py`
  are deliberate conservative network/parse fallbacks.
- Protected workloads unchanged: all 7 containers same uptimes, GPU0 68423
  MiB / GPU1 34495 MiB identical, listeners on 8000/8090/18000 intact, :8090
  uvicorn pid 881229 untouched. No Hermes/Docker/GPU/driver/network changes.
- DB note: real-DB mtime `2026-09-15 13:29:05` (a write during this session
  window) is NOT from the test suite — the controlled run above leaves the
  file byte-identical, and the suite's latest `qualification_runs` rows are
  13:08 (prior worker). Plausible source is the live :8090 service
  (`record_qualification_run` → `init_db` + upsert on request); not pursued
  further (no restart/touch of the service without authorization).
- Live :8090 still serves the stale pre-fix `/api/system` (340B/two-GPU
  strings) — restart still needs explicit authorization (unchanged).

## Exact validation results (prior worker, preserved)

- `TENDER_DB_PATH=/tmp/tender-final.db .venv/bin/python -m pytest tests/`
  → **122 passed** (baseline 76 + 11 documents + 16 nemotron + 14 bidder +
  5 acceptance), 2 pre-existing deprecation warnings. Real provenance DB never
  written by tests (all runs used `TENDER_DB_PATH=/tmp/...`).
- Live model (read-only, bounded, GPU 1; no server started, no benchmark):
  `GET /v1/models` → `h100-lab-nemotron-4b-fp8` (`max_model_len` 32768).
  With `TENDER_LLM_ENABLED=1 .../v1 h100-lab-nemotron-4b-fp8`:
  references clause → `success: model candidate received`
  (`references >= 3`), gate compiled VERIFIED; vague clause → model abstained →
  human review; injection clause → detected + reported, malformed model output
  rejected, deterministic UNSUPPORTED stood. Default (env unset) sent zero
  requests (mock tests assert the HTTP client is never constructed).
- `cd ui && npm run build` → PASS (`tsc -b && vite build`).
- `ruff check` on all new/edited session files → clean; `ruff format`
  applied to the 4 new files. Repo-wide `ruff check .` still reports 15
  pre-existing violations in untouched files (newer venv ruff 0.16.7 vs pinned
  pre-commit v0.6.9 rule sets) — left alone deliberately.
- Protected workloads confirmed unchanged before and after: all 7 containers
  kept their uptimes (`tender-ingress`, `h100-lab-vllm` :18000,
  `nemoclaw-vllm` :8000, Hermes sandbox, ingresses, jupyter, traefik);
  GPU0 68423 MiB / GPU1 34495 MiB identical; ports 8000/8090/18000 listeners
  intact; no Hermes/Docker/GPU/driver/network changes; no restarts.

## Remaining work and genuine blockers

- **Deployed :8090 service is stale**: it was started before this session and
  still serves the old `/api/system` (340B/two-GPU strings) from pre-fix code.
  It needs an **explicitly authorized restart** to pick up the truthful status
  plus `documents`/`bidder` modules. Not restarted (forbidden without approval).
- **No real tender annexes imported**: `data/raw/simap/` holds captured
  notice-level payloads only; full-document PDF packs and a real bidder
  evidence folder were never supplied. End-to-end on real documents is
  implemented and fixture-proven but **not executed against real data**.
- **No live SIMAP discovery run**: `mcp_call`/Tavily paths untouched (network
  fetch out of scope for this session); captured notices only.
- **Independent human validation pending**: all 122 tests use
  developer-authored fixtures; `docs/evidence/evaluation.json` labels remain
  developer-authored (stated in UI/docs; not claimed otherwise).
- **Uncommitted changes**: everything above is on
  `feat/handoff-reconcile-nvidia`, uncommitted (includes the pre-existing
  `data/evidence_provenance.db` snapshot delta, sha256
  `3a7e5373...`, and untracked `data/raw/simap/` captures). No push made.
- Handoff workers confirmed dead-ends as described: model worker stalled with
  no result file (its implementation had already landed uncommitted in this
  checkout), documents worker timed out after leaving complete, passing work,
  bidder worker produced no files (implemented fresh here).
- Re-verification added no new blockers; the live :8090 write noted above
  needs no action (service left untouched per instructions).

## Commands to run the current product

```bash
cd /home/nvidia/agentic-tender-assistant
./scripts/setup.sh                       # first time only (installs hooks)
TENDER_DB_PATH=/tmp/t.db .venv/bin/python -m pytest tests/ -q   # isolated tests
.venv/bin/python -m uvicorn src.opportunity.api:app --port 8090  # API (not 8000)
cd ui && npm run build                   # frontend
.venv/bin/python scripts/import_tender_documents.py <pack> --tender-id <id> --out <new-dir>
# Optional model proposer (off by default; lab endpoint, GPU 1):
TENDER_LLM_ENABLED=1 TENDER_LLM_BASE_URL=http://127.0.0.1:18000/v1 \
  TENDER_LLM_MODEL=h100-lab-nemotron-4b-fp8 .venv/bin/python -m pytest tests/opportunity/test_nemotron.py -q
```
