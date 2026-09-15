# Jury Demo — Tender Intelligence & Qualification System

**One-liner:** *We don't ask an LLM whether you qualify. We ask the LLM to understand the tender, then make the qualification independently verifiable.*

All companies, tenders and evidence in the demo corpus are synthetic. Real SIMAP
notices are replayed read-only in "captured" mode and are clearly labelled.

## Preparation

```bash
.venv/bin/python -m uvicorn src.opportunity.api:app --port 8090   # loopback API (never 8000: Hermes)
cd ui && npx vite build                                           # or: npm run dev
```

Open `http://127.0.0.1:8000` (serves the built UI). Data source: **Synthetic
walkthrough**. Scenario date: 2026-09-15. Company: Alpine Digital SA (fictional).

## 0:00 — The thesis

> LLMs are probabilistic. Procurement eligibility isn't. We use AI to understand
> tender language, then compile mandatory requirements into executable rules.

Point at any tender's **Compliance & evidence** table: every row carries the
**original clause** (verbatim), a **compiled rule** (`R5: insurance >= CHF
10,000,000 · MANDATORY · compiled VERIFIED`) and a **proof chain**
(CLAUSE → RULE → FACT → EVIDENCE → VERDICT).

## 0:20 — Find Opportunities

Click **Find Opportunities**. Four synthetic tenders are compiled and qualified:

| Tender | Value | Outcome | Why |
|---|---|---|---|
| IT Infrastructure Services | CHF 2.4M | GO | 4/4 mandatory checks proved |
| Data Platform Modernization | CHF 2.8M | CONDITIONAL | insurance evidence not yet found (4/5) |
| Security Operations Support | CHF 6.1M | NO-GO | ISO 20000 proved not held |
| Service Desk Operations | CHF 3.3M | NO-GO | evidence expires before the 2028 deadline |

## 0:40 — The heatmap

Every cell is a requirement family: 🟢 proved · 🔴 proved not met · 🟡 cannot
prove · – not required. Colour is never the only signal; text labels repeat it.

## 1:05 — Every green square carries a proof

Open the green **Certifications** cell on Infrastructure. Walk the chain:
clause text → compiled rule → company fact (ISO 27001, VERIFIED_INTERNAL) →
certificate file, line 3 → **PASS**.

## 1:40 — Yellow is an honest unknown, and evidence can resolve it

Data Platform's insurance cell is UNKNOWN: no verified company fact. Click
**Find evidence** — the knowledge folder yields the renewal certificate, the
rule re-evaluates: 🟡 → 🟢, CONDITIONAL GO → GO. The event log narrates every step.

## 2:10 — Minimum blocking set + deadline-aware remediation

Security Operations: the blocking set is exactly one requirement (ISO 20000).
Remediation carries a class (PARTNER OR SUBCONTRACT) and a deadline-feasibility
flag computed from stated lead-time assumptions — never invented certainties.

## 2:35 — Tender unit tests

On a tender detail page: *Requirements compiled 6 · 5 executable · 1 needs
review; generated tests 18/18 passing.* Boundary tests are generated from the
compiled rules (at threshold → PASS, below → FAIL, missing → UNKNOWN, expires
before deadline → FAIL). If the engine and a rule ever disagree, a generated
test fails. The **Evaluation** page aggregates this across the corpus
(compilation error rate, critical false PASSes, citation integrity).

## 3:10 — Qualification Landscape (competitors, same rules)

Open **Landscape**. Competitors are evaluated against the *same* compiled
requirements using public records only:

- **Our Company** (Alpine Digital SA) is pinned at the top row: verified against internal records.
- Helvetia IT — ISO 27001 in public registry: **PUBLICLY SUPPORTED**
- Alpen Technik — certificate publicly withdrawn: **PUBLIC NON-MATCH**
- Jura Consulting — no record found: **UNKNOWN** (never "cannot bid")
- Hewlett Packard Enterprise (HPE) — resolved canonical entity with public enterprise awards.

Every column analyzes **Competitive Requirement Advantage**:
- Low differentiation: standard requirements held by us and multiple competitors (e.g. ISO 27001).
- High differentiator: our company verified compliant while 0 competitors have public proof.
- Incumbent advantage: public award history identifies incumbent footprint for this buyer.

Click any cell: see the clean separation between **Public Observations** (awards, registry extracts) and **Derived Facts** (evaluating comparability against the tender clause).

## 3:35 — Capability gaps, what-if, portfolio

Open **Capability Gaps**: blockers aggregated across tenders with the
*potential tender value affected* (never "revenue unlocked"). Tick gaps →
**Run what-if simulation**: the pipeline recalculates under a **SIMULATION
ONLY** panel; verified state is untouched. Set bid capacity → **Plan
portfolio**: an explainable selection ranked by value per estimated bid day.

## 4:00 — Evaluation (controlled scope)

The **Evaluation** page reports the controlled developer-authored regression only
(`docs/evidence/evaluation.json`; independent human validation pending):
- Decision accuracy: 30/30 in the controlled set (see `cases`/`correct` fields).
- Compilation correctness: 22/22 in the controlled set (see
  `compilation_cases`/`compilation_correct` fields; error rate derived as
  `compilation_error_rate`).
- Critical false PASSes: 0 in the controlled set (see `critical_false_passes`);
  this is the observed count for these 30 cases, not a zero-failure guarantee.
- Unsupported factual claims: 0 in the controlled set (see
  `unsupported_factual_claims`); every checked fact traced to a source citation.
- Citations: 31/31 checked quotes verified verbatim in the controlled set (see
  `citations_checked`/`citations_verified`).
- Generated boundary unit tests: 57/57 passing in the controlled set (see
  `tender_tests_generated`/`tender_tests_passing`).
- Prompt-injection check (controlled): one in-corpus "IGNORE ALL PREVIOUS
  INSTRUCTIONS" clause is treated as passive text and the tested verdicts were
  unchanged (`injection_unchanged: true`). This is a scoped regression check,
  not immunity against prompt injection.

No business time-saving is claimed. Timing figures in the evaluation report are
developer planning estimates for the controlled synthetic corpus, not measured
customer outcomes; human verification of every proof chain is still required.

**Fallback:** stored real SIMAP notices also show per-requirement compile
outcomes. On the captured 15 September corpus, their notice-level criteria are
extracted verbatim with full JSON pointer citations, with 0 executable so far and the
remainder explicitly awaiting human review. This is honest partial extraction,
not a fabricated GO.

## 4:25 — System Architecture & Sovereign Story

Open **System** (status is backend-provided via `/api/system`; the UI asserts
no specific model or GPU deployment):
- **Candidate proposer:** local pattern matching, plus an optional bounded
  HTTP model proposer (`src/opportunity/nemotron.py`: OpenAI-compatible
  `/chat/completions`, strict JSON validation, timeouts, disabled by default).
  Candidate proposals never serve as the final eligibility judge — only the deterministic
  verifier decides.
- **Runtime:** NemoClaw / Hermes Agent Runtime with authenticated Streamable HTTPS endpoints.
- **Data Architecture:** Authoritative relational Evidence & Provenance Database (PostgreSQL schema at `data/schema.sql`, SQLite engine) tracking 13 tables (organizations, tenders, versions, requirements, evidence, facts, observations, derived claims, awards, runs, results).
- **Raw Storage:** Immutable raw source preservation under `data/raw/simap/`, `data/raw/company/`, `data/raw/competitors/`.
- **Deployment boundary (unverified in the UI):** no guarantee is made here that
  sensitive certificates, CVs, or financial data stay on-premise or never reach
  third-party APIs. Verify the backend and deployment configuration before
  loading real bidder data.

## 4:45 — Remaining real-data acceptance (not complete)

- Real bidder evidence is not configured: `/runs/{id}/evidence` refuses
  non-demo modes and states that synthetic certificates cannot qualify a real
  bidder. Real notices require verified company evidence before any GO/NO-GO.
- Stored real SIMAP notices have notice-level extraction only (0 executable
  rules so far on the captured corpus); full annexes still require human review.
- End-to-end acceptance still required: discovery → documents → cited
  requirements → verified company evidence → decision, including a real
  amendment and FR/DE/IT coverage.
- Independent human labeling of external live documents is pending; current
  figures are controlled developer-authored regression only.

## 4:50 — Close

> Every green square carries a proof, every red square names the exact blocking
> requirement, and every yellow square says what evidence is missing. That is
> the product.
