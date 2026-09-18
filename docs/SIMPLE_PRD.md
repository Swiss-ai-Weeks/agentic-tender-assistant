# Simple PRD — Agentic Tender Assistant

## 1. Product goal

Help a Swiss SME decide whether to pursue a public tender. The application finds
relevant SIMAP opportunities, reads their notices and documents, compares mandatory
requirements with one company profile, and produces a cited GO / REVIEW / NO-GO briefing.

The product supports qualification; it does not write or submit the bid.

## 2. MVP user flow

1. The user creates one company profile: services, locations, languages,
   certifications, references, revenue/capacity, and preferred tender keywords.
2. The user searches SIMAP through the existing SIMAP MCP tool available to Hermes.
3. The workflow fetches the selected tender and its available documents through SIMAP
   MCP. A pasted tender URL/ID is the fallback input.
4. The application extracts the deadline, scope, mandatory requirements, award
   criteria, and required evidence. Every extracted claim links to its source.
5. Deterministic rules compare mandatory requirements with verified company evidence.
6. The application displays a qualification briefing and lets the user record the
   final decision.

## 3. MVP output

Each briefing contains:

- tender title, buyer, location, language, source URL, and submission deadline;
- short scope summary;
- mandatory-requirement checklist with MET / NOT MET / UNKNOWN status;
- award criteria and weights when published;
- missing evidence, risks, and questions requiring human review;
- GO / REVIEW / NO-GO recommendation with a short explanation;
- document, page/section, and exact-quote citations for material claims.

Safety rule: missing or ambiguous evidence is UNKNOWN, never MET. The LLM may extract
and explain candidate facts, but only deterministic checks produce eligibility status.

## 4. Simplest architecture

Use one NeMo Agent Toolkit workflow rather than several autonomous agents:

`SIMAP MCP -> document extraction -> structured LLM extraction -> deterministic checks -> briefing`

- **Frontend:** existing React/Vite application.
- **Orchestration:** NeMo Agent Toolkit is the primary application layer. Implement one
  registered workflow with a small set of reusable NAT functions; run it with `nat run`
  and optionally expose it through the NAT MCP frontend.
- **SIMAP access:** consume the SIMAP MCP already registered in Hermes. Do not build a
  second SIMAP scraper or MCP server. First verify its actual tool names and response
  schema, then isolate them behind one typed Python adapter.
- **Backend/UI bridge:** keep FastAPI only as a thin React-to-NAT adapter. Business logic
  stays in workflow functions.
- **Models/contracts:** existing Pydantic opportunity models.
- **Storage:** SQLite for the MVP; immutable source files plus hashes for provenance.
- **Document parsing:** `pypdf` for text PDFs. Flag scanned/encrypted files for review.
- **AI:** one OpenAI-compatible model endpoint, optionally served by NVIDIA/Nemotron.
- **Hermes/NemoClaw:** use Hermes as the conversational entrypoint and tool caller; NAT
  remains responsible for the repeatable qualification workflow.

The MVP has one fixed-sequence NAT workflow and four functions: `search_simap`,
`load_tender`, `qualify_tender`, and `build_briefing`. Separate autonomous agents
are not required.

No vector database is needed for the MVP. Tender packs are small enough to chunk and
process per document, while retaining source/page metadata.

## 5. Keep from the current repository

- `src/opportunity/`: working API, document ingestion, provenance, compiler,
  deterministic engine, SIMAP support, briefing, and model adapter.
- `ui/`: current React interface; reduce it to profile, search/results, and briefing.
- `tests/opportunity/`: behavior and safety coverage for the working product.
- `data/company_profile.example.json` and `data/schema.sql`.
- `scripts/import_tender_documents.py`.
- `pyproject.toml`, `.env.example`, `.gitignore`, lint/test configuration.
- `docs/JURY_DEMO.md` and `docs/architecture.md`, after aligning them with this MVP.
- One NeMo configuration only when it invokes the real workflow.

## 6. Remove or archive

Remove in a dedicated cleanup PR after confirming no imports depend on them:

- Legacy stub implementations under `src/agents/`; retain or replace `src/pipeline.py`
  as the single NAT component-registration module.
- `tests/agents/` and tests that only assert `NotImplementedError`.
- `src/schemas/` if its contracts are used only by the legacy path.
- obsolete NeMo configs that point at the stubbed multi-agent pipeline or Tavily search.
- the local SIMAP stdio bridge/package under `integrations/simap/` after the Hermes MCP
  connection is verified; it duplicates the available service.
- duplicate/outdated planning documents (`CHALLENGE.md` versus `docs/CHALLENGE.md`,
  `RESUME_STATUS.md`, and environment-specific implementation notes) after preserving
  any still-useful setup instructions.
- tracked demo/runtime outputs or databases that can be regenerated. Keep only small,
  anonymized fixtures required by tests.

Do not commit `.env`, `.runtime/`, caches, virtual environments, generated frontend
files, real bidder evidence, or downloaded tender packs.

## 7. Functional requirements

- Search SIMAP via its existing MCP tools using keywords and basic filters, with manual
  URL/ID input as fallback.
- Normalize MCP responses behind one typed adapter.
- Import PDF and text documents without silently skipping unreadable files.
- Extract structured fields with source citations and confidence/review status.
- Compare requirements against an editable company profile and verified evidence.
- Generate and export a human-readable JSON/HTML briefing.
- Preserve the original source/version and detect changed documents on re-import.
- Allow a user to override and record the final pursuit decision.

## 8. Non-goals for MVP

- autonomous bid writing or submission;
- multi-company tenancy, authentication, billing, or notifications;
- Tavily/general web search, competitor intelligence, and portfolio optimization;
- OCR for every scanned format;
- a swarm of agents or long-term conversational memory.

## 9. Delivery plan

### Phase 1 — Verify integration and simplify (1–2 days)

- From Hermes, list and call the SIMAP MCP tools with one known tender; save response
  fixtures for offline tests.
- Replace the stubbed NAT path with one registered workflow exposed through `nat run`.
- Select three anonymized tender packs and one company profile as fixtures.
- Make the existing tests and UI build the CI baseline.

### Phase 2 — Complete one vertical slice (2–4 days)

- Connect SIMAP MCP search/details to document extraction and cited structured fields.
- Connect extracted mandatory clauses to the existing deterministic engine.
- Return one stable briefing schema through the API and render it in the UI.

### Phase 3 — Polish and demo through Hermes (1–2 days)

- Add source links, review states, decision capture, export, and clear error handling.
- Expose the NAT workflow as a Hermes-callable tool if needed and demonstrate
  search-to-briefing from Hermes and the UI.

## 10. MVP acceptance criteria

- A user can take one real tender from search/import to briefing in under two minutes,
  excluding unusually large downloads.
- Deadline and all mandatory requirements shown in the briefing have working citations.
- Missing, conflicting, unreadable, or ambiguous evidence cannot result in MET or GO.
- The same inputs produce the same eligibility verdicts.
- At least one French or German tender is processed without translating away citations.
- Backend tests pass and the production frontend builds from a clean checkout.
- The primary demo executes through NeMo Agent Toolkit and the existing SIMAP MCP, not
  the repository's local SIMAP bridge.

## 11. Main risks

- SIMAP MCP availability, tool-name, schema, or document-link changes: verify the live
  capability first, isolate it behind one adapter, save fixtures, and retain manual
  import as a fallback.
- LLM extraction errors: require exact citations, schema validation, and human-review
  states; keep verdicts deterministic.
- Scanned or incomplete document packs: visibly block a confident GO recommendation.
- Poor company data: distinguish self-declared profile facts from verified evidence.
