PRD — Agentic Tender Assistant

Status: Draft v2 — Hackathon (HPE & NVIDIA Agentic AI Hackathon, Swiss AI Weeks) Owner: Team (3 engineers)

Implementation status note (2026-09-15): the working product entrypoint is
`src/opportunity/` (API + deterministic engine/compiler/provenance DB) plus
the `ui/` frontend — see README "Current product entrypoint" and
`docs/JURY_DEMO.md`. The `src/agents/` + `src/pipeline.py` multi-agent
pipeline described in sections 6–7 below is the preserved historical scaffold:
those modules remain stubbed (`NotImplementedError`) and do not run. Sections
4–7 are kept as the original product/architectural intent, not as claims about
what runs today. Evaluation scope throughout is the controlled
developer-authored set (`docs/evidence/evaluation.json`); independent human
validation is pending.

1. Executive Summary

A go/no-bid decision assistant for Swiss public tenders. It connects directly to simap.ch via the SIMAP MCP server (no scraping required — simap exposes a public, read-only API), extracts and cites every eligibility rule, deadline, and award criterion from the tender documents, and produces a structured, defensible qualification briefing. Where information isn't available on simap itself (buyer background, sector context, unclear terminology), the system uses Tavily for live web enrichment — always kept visibly separate from grounded document facts.

2. Why Switzerland — Market Context
Swiss public procurement is fragmented across Confederation, 26 cantons, and communes, all publishing through the single official channel, simap.ch — but with very different institutions, thresholds, and languages issuing notices.
Publications happen in French, German, and Italian depending on the issuing authority, with no guarantee of translation.
The Swiss economy is SME-dominated; most companies bidding on public tenders do not have a dedicated proposal/bid team — the same person doing delivery work is also reading tenders on the side.
simap.ch has no live scraping-friendly UI for automation (legacy session-based JSP portal), but it does expose a public, unauthenticated, read-only API — which is the actual integration point, not the website.

This is not a generic "AI RFP tool" repositioned for Switzerland — it's designed around the specific shape of the Swiss procurement landscape: multilingual, decentralized, SME-heavy, and API-accessible in a way most people don't realize.

3. Who This Is For
Primary persona — "The Accidental Bid Owner"

A partner, ops lead, or senior engineer at a Swiss SME or mid-market firm (engineering, IT services, construction, consulting) who reviews public tenders alongside their main job, not as a full-time role. They:

Don't have time to read every tender end-to-end
Have been burned before by a missed eligibility criterion or deadline
Need a fast, trustworthy go/no-go signal they can act on or forward to a colleague
Work across languages (may read French fluently but not German, or vice versa)
Secondary persona — "The Bid/Procurement Consultant"

An external consultant or small agency helping several client companies monitor and qualify tenders. They need to manage multiple company profiles and see tenders triaged per client, not just per document.

Explicitly NOT the target (v1)
The buyer/adjudicator side (drafting or publishing tenders) — out of scope entirely
Large enterprises with dedicated 10+ person bid teams — they already have proposal-drafting tooling (Loopio/Responsive-style); our differentiation is upstream of that, at triage and eligibility, and isn't where they feel the most pain
Full proposal/response drafting — writing the actual bid content is a separate, already-crowded problem; we stop at the qualification briefing and go/no-go decision
4. Tool & Technology Stack
Layer	Tool	Role
Tender discovery & monitoring	SIMAP MCP (@digilac/simap-mcp, MIT, official MCP registry)	Structured, official access to simap.ch: search_tenders (text, dates, type, canton, CPV filters), get_tender_details, get_publication_history (corrigenda/change detection), list_cantons, list_institutions, search_proc_offices, plus CPV/BKP/NPK/OAG code lookup and hierarchy tools for precise sector matching
Web enrichment	Tavily	Real-time web search/extract for context not present on simap: buyer background, clarifying an ambiguous technical/sector term, checking a public registry or certification the tender references. Always labeled as external context, never merged into "extracted facts" from the tender documents
Document parsing	Ingestion agent (PDF/text extraction)	Parses the cahier des charges + annexes linked from get_tender_details; simap's API gives structured metadata, not the full text of every annex, so this layer still does the heavy reading
Agent orchestration / runtime	NVIDIA NeMo Agent Toolkit, optionally NemoClaw for sandboxing	Orchestrates the multi-agent pipeline; NemoClaw's OpenShell sandbox scopes what each agent can access (tender docs + company profile only)
Structured data contracts	Pydantic	Shared schemas between agents (extracted tender, company profile, briefing)

Key implication for architecture: discovery is no longer "scrape simap or wait" — it's a first-class MCP tool call. This removes the biggest technical risk we'd previously flagged and lets us support live monitoring (via get_publication_history) as a real MVP feature, not a stretch goal.

5. Pain Point → Requirement Mapping (Swiss-specific)
Pain point	Requirement	Enabled by
Manually checking simap for relevant new tenders	Automated, filterable discovery matched to company profile (CPV/BKP codes, cantons, keywords)	SIMAP MCP search_tenders, search_cpv_codes/browse_cpv_tree
Disqualification on missed eligibility criteria	Deterministic eligibility gate; each criterion marked met / unmet / unclear, sourced to the document	Extraction agent + eligibility gate agent
Deadlines buried across notice + annexes	All deadlines surfaced in one place, cited	Extraction agent
Tenders published in FR/DE/IT depending on canton	Language-agnostic extraction; briefing always rendered in the user's chosen language	Extraction agent + LLM
Tender terms change after publication (corrigenda)	Automatic re-check and diff for tenders already briefed	SIMAP MCP get_publication_history
Missing context not on simap (buyer history, unclear terms)	On-demand web enrichment, clearly separated from grounded facts	Tavily
No dedicated bid role at SMEs — one overloaded person	UX built for a 5-minute decision, not a dashboard requiring daily attention	UX design (see below)
Managing several client profiles (consultant persona)	Multi-profile support, per-client triage views	Company profile schema (see below)
6. Architecture (Multi-Agent Pipeline)
Discovery & monitoring agent — calls SIMAP MCP (search_tenders filtered by the company profile's CPV/BKP codes, cantons, and keywords) to build a ranked candidate list; calls get_publication_history on tenders already briefed to detect corrigenda.
Ingestion & extraction agent — pulls full tender details (get_tender_details), downloads and parses linked documents, extracts deadlines, eligibility criteria, and weighted award criteria — every field cited to page/section.
Enrichment agent (Tavily, optional) — fills gaps not covered by simap data (buyer context, terminology), tagged as "external context" in the output, never as a grounded requirement.
Eligibility gate agent — deterministic pass/fail of eligibility criteria against the company profile. Never a soft LLM judgment call.
Fit scoring agent — weighted score against award criteria, runs only if the eligibility gate passes.
Briefing generation agent — produces the final structured qualification briefing: summary, deadlines, eligibility status per criterion, award criteria breakdown, risks/ flags, go/no-go recommendation with justification, and a clearly marked "external context" section if Tavily was used.
7. UX & User Journeys
Design principle

The target user has a few minutes, not a few hours. Every screen should answer "what do I need to know or decide right now?" — not present a data-heavy dashboard by default.

Journey A — Accidental Bid Owner (primary)
One-time setup: fill a short company profile — sector/CPV codes, cantons of interest, certifications, key references, capacity, preferred output language. Framed as "tell us once, we'll match automatically" — not a long onboarding form.
Weekly digest / triage list: a short, ranked list of new or updated tenders matching the profile — each row shows fit score, eligibility status (✅/⚠️/❌), and deadline. Designed to be scannable in under a minute.
One-click deep dive: clicking a tender produces the full qualification briefing — eligibility checklist with citations, award criteria breakdown, risks, and a clear go/no-go recommendation with reasoning in plain language.
Decision capture: user confirms or overrides the recommendation with one click; the decision + reasoning is saved for future audit ("why did we skip this one?").
Change alerts: if a tender under review is amended (corrigenda), the user gets a flag showing exactly what changed, not a re-read of the whole document.
Journey B — Bid/Procurement Consultant (secondary)
Multi-client switcher: select which client's company profile is active.
Portfolio view: tenders triaged across all managed clients at once, so the consultant can prioritize where to spend their limited hours across accounts.
Same deep-dive/briefing/decision flow as Journey A, scoped per client.
Key UX/trust rule

Anywhere the briefing shows a fact, it must be visually traceable to its source (document + section) on hover/click. Anything from Tavily enrichment is visually distinct (e.g., a different badge/color) from anything extracted from the tender documents themselves — this is a trust feature, not a cosmetic one, and should be non-negotiable in the demo.

8. Non-Goals (out of scope for hackathon MVP)
Drafting the actual bid/proposal response content
Submission/filing automation
Long-term cross-session "agent memory" beyond the reusable company profile and tender history (see earlier discussion — a database, not a memory framework)
Full multi-tenant production auth/billing (single or few demo profiles is enough)
9. Success Metrics (for the demo — controlled scope; independent human validation pending)
Time from tender selection to full briefing: under 2 minutes
Eligibility criteria in the controlled demo set classified met/unmet/unclear with zero false "met" observed in that set (see `critical_false_passes`; not a zero-failure guarantee)
Extracted facts (deadlines, criteria) in the controlled set carry a source citation (see `citations_checked`/`citations_verified`)
At least one live corrigenda-detection example shown via get_publication_history
Judges can pick any claim in the briefing and trace it back to the exact source

Remaining real-data acceptance (not complete, not claimed as done): real bidder
evidence is not configured (synthetic demo evidence cannot qualify a real
bidder); stored real SIMAP notices have notice-level extraction only with full
annexes still requiring human review; end-to-end discovery → documents → cited
requirements → verified evidence → decision (including a real amendment and
FR/DE/IT coverage) is still required. No business time-saving is claimed;
timing figures are developer planning estimates for the controlled corpus.
10. Risks & Assumptions
Risk: LLM extraction misreads an eligibility criterion → mitigated by requiring citation for every field; unclear cases are flagged, never silently marked "met"
Risk: SIMAP MCP is a community project (Digilac, MIT license), not an official government API client — depends on simap's public API remaining stable and available during the demo window
Risk: Tavily enrichment could introduce unverified information if not clearly separated from document-grounded facts → strict UI/data separation is a hard requirement, not a nice-to-have
Assumption: A structured company profile (certifications, references, capacity) is accurate — profile quality bounds gate accuracy