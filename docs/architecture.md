# Architecture

## Pipeline

1. **Ingestion & Extraction Agent**
   - Input: a tender's document set (notice, cahier des charges, annexes), any
     of FR/DE/IT.
   - Output: `ExtractedTenderData` — deadlines, eligibility criteria, award
     criteria + weights, mandatory documents to submit. Every field carries a
     `Citation` (document name + page/section).
   - Owner: Track A.

2. **Eligibility Gate Agent**
   - Input: `ExtractedTenderData.eligibility_criteria` + `CompanyProfile`.
   - Output: `list[EligibilityResult]` — deterministic pass/fail/unknown per
     criterion, each with a justification.
   - Intentionally deterministic/rule-based, not left to model judgment — a
     missed eligibility criterion disqualifies the bid outright, so this step
     should not be subject to probabilistic drift.
   - Owner: Track B.

3. **Fit Scoring Agent**
   - Only runs if the eligibility gate passes all mandatory criteria.
   - Input: `ExtractedTenderData.award_criteria` + `CompanyProfile`.
   - Output: `list[AwardCriterionScore]` — a 0–100 fit score per award
     criterion plus its weighted contribution.
   - Owner: Track B.

4. **Briefing Generation Agent**
   - Input: tender data, eligibility results, gate outcome, award scores.
   - Output: `QualificationBriefing` — summary, deadlines, eligibility status
     per criterion, award criteria breakdown, risk flags, go/no-go
     recommendation + justification.
   - Owner: Track C.

5. **(Stretch) Monitoring Agent** — detects corrigenda/updates to a tender
   already under review, diffs against the previously extracted data, and
   re-triggers the pipeline on material changes. Not in scope for the
   hackathon skeleton.

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

## Orchestration: NeMo Agent Toolkit vs. custom orchestrator

The brief asks for the NVIDIA NeMo Agent Toolkit "where practical," falling
back to a simple custom orchestrator if setup friction is too high for
hackathon time.

**Decision for the skeleton stage:** `src/pipeline.py` wires the four agents
together with plain Python function calls (`run_pipeline`) — no orchestration
framework dependency yet. Rationale:

- There's no working agent logic yet, so there's nothing for an orchestration
  framework to add value to right now; adopting one before validating
  LLM provider/access just adds unvalidated setup surface.
- Plain function composition keeps the three tracks' interfaces (the Pydantic
  schemas) framework-agnostic, so adopting NeMo Agent Toolkit later is a
  `pipeline.py`-only change, not a schema/agent rewrite.

Revisit once ingestion/eligibility/scoring have real logic and we've confirmed
NeMo Agent Toolkit setup cost fits the remaining hackathon time. If adopted,
`pipeline.py` should be the only file that needs to change.

## Input format (hackathon demo)

Live scraping of simap.ch is a stretch goal, not a blocker — simap.ch has no
public API. For the demo, tenders are a local folder of PDFs per
`data/sample_tenders/README.md`.
