# Jury Demo — Tender Intelligence & Qualification System

**One-liner:** *We don't ask an LLM whether you qualify. We ask the LLM to understand the tender, then make the qualification independently verifiable.*

All companies, tenders and evidence in the demo corpus are synthetic. Real SIMAP
notices are replayed read-only in "captured" mode and are clearly labelled.

## Preparation

```bash
.venv/bin/python -m uvicorn src.opportunity.api:app --port 8000   # loopback API
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

- Helvetia IT — ISO 27001 in public registry: **PUBLICLY SUPPORTED**
- Alpen Technik — certificate publicly withdrawn: **PUBLIC NON-MATCH**
- Jura Consulting — no record found: **UNKNOWN** (never "cannot bid")

Entity resolution maps award entries like "Helvetia IT" to the canonical
organization. Comparable-award counting respects the tender's 5-year window.

## 3:35 — Capability gaps, what-if, portfolio

Open **Capability Gaps**: blockers aggregated across tenders with the
*potential tender value affected* (never "revenue unlocked"). Tick gaps →
**Run what-if simulation**: the pipeline recalculates under a **SIMULATION
ONLY** panel; verified state is untouched. Set bid capacity → **Plan
portfolio**: an explainable selection ranked by value per estimated bid day.

## 4:00 — Evaluation

The **Evaluation** page: 30/30 decision cases, 17/17 compilation cases,
compilation error rate 0, zero critical false PASSes, 31/31 citations verified
verbatim, prompt-injection invariance (an in-corpus "IGNORE ALL PREVIOUS
INSTRUCTIONS" clause changes nothing). Scope and unmeasured items are stated.

## 4:25 — Architecture

SIMAP (read-only MCP) → Tender Compiler (clause → executable IR, AMBIGUOUS
stays ambiguous; Nemotron/H100 is the planned semantic proposer behind the
deterministic validation gate) → evidence graph (facts ≠ evidence, trust
classes, validity windows) → deterministic engine (PASS/FAIL/UNKNOWN) →
proof, blockers, landscape. Raw sources are stored immutably per tender
version (`data/raw/simap/tender_<id>/version_NNN`).

## 4:50 — Close

> Every green square carries a proof, every red square names the exact blocking
> requirement, and every yellow square says what evidence is missing. That is
> the product.
