"""Track A (stretch) — live tender discovery via Tavily web search.

Finds candidate tenders in the first place — CHALLENGE.md's "Identify
relevant tenders" step — distinct from ingestion.py, which extracts
requirements from PDFs a human already has.

Tavily is also NemoClaw/Hermes's own native web-search backend for this
project's sandbox (see docs/aiq-blueprint.md "Hermes's native Tavily web
search" — NemoClaw's `tavily` network-policy preset permits exactly
`POST /search` and `POST /extract` to `api.tavily.com`, matching what this
module calls). Calling Tavily directly here — rather than through the
separately-running AI-Q Blueprint (docs/aiq-blueprint.md) — keeps one search
provider across both the coding-agent side (Hermes) and the product side
(this pipeline), and avoids that isolated process for search specifically.
The AI-Q Blueprint remains available for deeper, multi-step research
synthesis if the team wants it later; it's no longer on this module's path.

Two-tier design: a broad shallow pass restricted to simap.ch, then an
advanced-depth deep pass scoped to the company's capabilities. Every lead is
one real Tavily search result — a genuine per-fact citation (the actual
result URL/snippet), not a synthesized report summary.

Needs TAVILY_API_KEY — see .env.example.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx

from src.schemas.common import Citation
from src.schemas.company import CompanyProfile
from src.schemas.discovery import TenderLead

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
SIMAP_DOMAINS = ["simap.ch", "www.simap.ch"]
SHALLOW_MAX_RESULTS = 5
DEEP_MAX_RESULTS = 5


def _api_key() -> str:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not set — see .env.example")
    return key


async def _search(
    client: httpx.AsyncClient, query: str, *, depth: str, max_results: int
) -> list[dict[str, Any]]:
    response = await client.post(
        TAVILY_SEARCH_URL,
        json={
            "api_key": _api_key(),
            "query": query,
            "search_depth": depth,
            "max_results": max_results,
            "include_domains": SIMAP_DOMAINS,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("results", [])


def _lead_from_result(result: dict[str, Any], *, relevance_note: str | None) -> TenderLead:
    content = result.get("content") or ""
    return TenderLead(
        title=result.get("title") or result.get("url", "Untitled tender"),
        url=result["url"],
        summary=content[:2000],
        relevance_note=relevance_note,
        citation=Citation(document=result["url"], quote=content[:280] or None),
        found_at=datetime.now(UTC),
    )


async def discover_tenders(query: str, company: CompanyProfile) -> list[TenderLead]:
    """Shallow-then-deep tender search via Tavily, restricted to simap.ch.

    Shallow pass: broad, basic-depth search for candidate leads.
    Deep pass: advanced-depth search on a query scoped to the company's
    capabilities, for richer content on the most relevant matches.
    Returns one TenderLead per real Tavily result across both passes.
    """
    async with httpx.AsyncClient() as client:
        shallow_results = await _search(client, query, depth="basic", max_results=SHALLOW_MAX_RESULTS)

        capability_hint = ", ".join(company.capabilities) or "general services"
        deep_query = f"{query} {capability_hint}"
        deep_results = await _search(client, deep_query, depth="advanced", max_results=DEEP_MAX_RESULTS)

    leads = [_lead_from_result(r, relevance_note=None) for r in shallow_results]
    leads += [
        _lead_from_result(r, relevance_note=f"Matched against capabilities: {capability_hint}")
        for r in deep_results
    ]
    return leads
