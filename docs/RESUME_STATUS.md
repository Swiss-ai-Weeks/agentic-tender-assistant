# Tender project resumption audit

## Goal

Build a Swiss public-tender opportunity and qualification assistant: discover SIMAP
opportunities, read supporting documents, compile cited requirements, compare against
verified company evidence, and produce defensible GO/NO-GO/UNKNOWN briefings.
Competitive landscape, remediation/what-if and portfolio selection support the decision.
Never fabricate evidence, treat missing public evidence as disqualification, or let a
model override mandatory eligibility checks.

## Verified current state

Local checkout: ede4fe7 at audit start; clean working tree before this note.
Local test run: 76 passed, 2 dependency deprecation warnings (0.84 seconds).
Evidence: .runtime/tender-resume-tests.txt.
The opportunity layer includes compiler, deterministic engine, provenance DB,
competitor/strategy modules, SIMAP adapter, APIs and UI. Historical evaluation is
30 controlled developer-authored cases; independent human validation is pending.

## Remaining priorities

1. Real semantic model integration and truthful runtime status. `nemotron.py` currently
   proposes candidates with regex; its configured model/URL are not called. `/api/system`
   nonetheless claims Nemotron-4-340B on two H100s. Remove unsupported claims and wire
   an actual independently configured model candidate proposer through the verifier.
   Do not modify Hermes or reuse its occupied GPU. The lab endpoint is an available
   integration candidate, subject to fresh read-only verification.
2. Real tender document/annex extraction and real company evidence. Demo evidence is
   synthetic; real notices explicitly require review. Do not report the synthetic
   decision cases as complete qualification of real tenders.
3. End-to-end real tender acceptance: discovery → documents → cited requirements →
   company evidence → decision, including a real amendment and FR/DE/IT coverage.
4. Independent labeled evaluation and honest performance/impact claims. Existing
   JURY_DEMO prose overstates the model deployment and measured business impact.
5. Reconcile old stubs/README/PRD with the active opportunity implementation. The old
   src/agents ingestion, eligibility, fit and briefing functions remain stubs; choose
   a single documented product entrypoint rather than suggesting these run today.

Deployment, current remote checkout and rendered UI have not been revalidated during
this resumption audit. Do not push, publish or modify remote services based on this note.

Delegation preference: agy Gemini 3.8 Flash High → Cursor Grok 4.6 Extra High →
OpenCode Muse Spark 1.3 contributor-free → Codex. Exclude ZCode/GLM.
