"""Competitive qualification landscape and candidate generation.

The exact compiled requirement set of a tender is evaluated for competitor
organizations using public evidence only.

Core principles:
- Observation vs. Derived Claim: Public observations (awards, registry filings)
  are strictly separated from derived qualification claims.
- Status Semantics:
  PUBLICLY SUPPORTED: Public record proves the compiled rule.
  PUBLIC NON-MATCH: Public record directly contradicts the compiled rule.
  UNKNOWN: Insufficient public evidence. NEVER interpreted as inability to bid.
- Entity Resolution: Canonical resolution across official names, aliases,
  domains and registry identifiers (UIDs).
- Competitor Candidate Generation: Identifies likely competitors from buyer history,
  incumbent contracts, CPV/category matching, and past SIMAP awards.
- Competitive Requirement Advantage: Evaluates whether each requirement is a
  differentiator, a commodity barrier, or indicates potential incumbent advantage.
"""
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field

from src.opportunity.facts import competitor_data, resolve_org
from src.opportunity.models import CompetitorStatus

SOURCE_TYPE = "public record"


class PublicObservation(BaseModel):
    id: str
    organization: str
    observation_type: str  # 'award', 'certificate_registry', 'commercial_registry'
    title: str
    description: str = ""
    buyer: str = ""
    date: str
    value_chf: float | None = None
    source_document: str
    source_quote: str
    source_url: str
    trust: str = "VERIFIED_PUBLIC"
    observed_at: str = Field(default_factory=lambda: datetime.now(UTC).date().isoformat())


class DerivedFact(BaseModel):
    id: str
    organization: str
    predicate: str
    claim_summary: str
    comparability_rationale: str
    is_supported: bool
    observation_ref: str
    trust: str = "INFERRED"


class CompetitorCandidate(BaseModel):
    org_id: str
    name: str
    rationale: str
    category: str  # 'incumbent', 'category_winner', 'domain_specialist'
    evidence_count: int
    latest_award_date: str | None = None


def resolve_organization(name_or_id: str) -> dict | None:
    """Enhanced entity resolution supporting canonical names, aliases, domains, and UIDs."""
    data = competitor_data()
    needle = name_or_id.casefold().strip()

    # Direct ID or registry ID match
    for org in data.get("orgs", []):
        if org.get("id", "").casefold() == needle:
            return org
        if org.get("registry_id", "").casefold() == needle:
            return org

    return resolve_org(name_or_id, data.get("orgs", []))


def _award_comparable(award: dict, scope: str) -> tuple[bool, str]:
    """Deterministic comparability proxy: keyword overlap between the award
    description and the tender scope."""
    text = (award.get("description", "") + " " + award.get("title", "")).casefold()
    words = [w for w in scope.casefold().replace(",", " ").replace(";", " ").split() if len(w) > 3]
    matches = [w for w in words if w in text]
    if matches:
        return True, f"Keyword overlap in published award scope: {', '.join(matches[:3])}"
    return False, "No keyword overlap between award description and tender scope"


def generate_competitor_candidates(scope: str, buyer: str) -> list[dict]:
    """Generate likely relevant competitor candidates from public SIMAP award history.

    Identifies incumbent suppliers (who previously won contracts with this buyer)
    and category winners (who won similar contracts).
    """
    data = competitor_data()
    candidates: dict[str, dict] = {}
    buyer_clean = buyer.casefold()

    for award in data.get("awards", []):
        resolved = resolve_organization(award.get("org", ""))
        if not resolved:
            continue
        org_id = resolved["id"]
        org_name = resolved["name"]

        is_incumbent = buyer_clean in award.get("buyer", "").casefold() or award.get("buyer", "").casefold() in buyer_clean
        is_comparable, _rationale = _award_comparable(award, scope)

        if is_incumbent or is_comparable:
            cand = candidates.setdefault(
                org_id,
                {
                    "org_id": org_id,
                    "name": org_name,
                    "registry_id": resolved.get("registry_id"),
                    "reasons": [],
                    "award_count": 0,
                    "latest_award": award.get("date"),
                    "incumbent": False,
                },
            )
            cand["award_count"] += 1
            if is_incumbent:
                cand["incumbent"] = True
                cand["reasons"].append(f"Incumbent supplier: past contract with {award.get('buyer')} ({award.get('title')})")
            if is_comparable:
                cand["reasons"].append(f"Comparable scope: '{award.get('title')}' ({award.get('date')})")
            cand["latest_award"] = max(cand["latest_award"], award.get("date"))

    result = []
    for cand in candidates.values():
        category = "Incumbent supplier" if cand["incumbent"] else "Market competitor"
        summary_rationale = "; ".join(cand["reasons"][:2])
        result.append({
            "org_id": cand["org_id"],
            "name": cand["name"],
            "registry_id": cand["registry_id"],
            "category": category,
            "rationale": summary_rationale,
            "award_count": cand["award_count"],
            "latest_award": cand["latest_award"],
        })

    return sorted(result, key=lambda c: (0 if c["category"] == "Incumbent supplier" else 1, -c["award_count"]))


def _reference_state(
    org_id: str,
    expected: float,
    window_years: int | None,
    deadline: str | None,
    awards: list[dict],
    scope: str,
) -> tuple[CompetitorStatus, str, list[dict], list[dict], list[dict]]:
    """Evaluates comparable references with explicit separation between
    Observations and Derived Facts."""
    cut = None
    if window_years and deadline:
        cut = (date.fromisoformat(deadline).replace(year=date.fromisoformat(deadline).year - window_years)).isoformat()

    observations = []
    derived_facts = []
    comparable_count = 0

    for award in awards:
        resolved = resolve_organization(award.get("org", ""))
        if not resolved or resolved["id"] != org_id:
            continue

        obs = {
            "title": award.get("title", ""),
            "buyer": award.get("buyer", ""),
            "date": award.get("date", ""),
            "value_chf": award.get("value_chf"),
            "document": award["source"]["document"],
            "quote": award["source"]["quote"],
            "url": f"/api/sources/competitors/{award['source']['document']}",
            "trust": "VERIFIED_PUBLIC",
        }
        observations.append(obs)

        # Check recency window
        if cut and award["date"] < cut:
            derived_facts.append({
                "predicate": "references",
                "claim": f"Award outside {window_years}-year window (awarded {award['date']} < deadline threshold {cut})",
                "is_supported": False,
                "document": award["source"]["document"],
            })
            continue

        # Check comparability
        is_comp, rationale = _award_comparable(award, scope)
        if is_comp:
            comparable_count += 1
            derived_facts.append({
                "predicate": "references",
                "claim": f"Award satisfies comparable-reference criterion: {rationale}",
                "is_supported": True,
                "document": award["source"]["document"],
            })

    evidence = [
        {
            "document": obs["document"],
            "quote": obs["quote"],
            "url": obs["url"],
            "trust": "VERIFIED_PUBLIC",
        }
        for obs in observations
        if any(df["is_supported"] for df in derived_facts if df["document"] == obs["document"])
    ]

    if comparable_count >= expected:
        note = f"{comparable_count} comparable public awards on record (threshold {expected:.0f})."
        return "PUBLICLY SUPPORTED", note, evidence, observations, derived_facts

    note = (
        f"{comparable_count} comparable public awards found (threshold {expected:.0f}); "
        "public registers are not exhaustive, so absence of more awards proves nothing."
    )
    return "UNKNOWN", note, evidence, observations, derived_facts


def _registry_state(
    org_id: str, requirement_field: str, expected: Any
) -> tuple[CompetitorStatus, str, list[dict], list[dict], list[dict]]:
    """Evaluates public registry records with explicit separation between
    Observations and Derived Facts."""
    data = competitor_data()
    matching = []
    for fact in data.get("registry_facts", []):
        resolved = resolve_organization(fact.get("org", ""))
        if resolved and resolved["id"] == org_id and fact["predicate"] == requirement_field:
            matching.append(fact)

    observations = []
    derived_facts = []

    for f in matching:
        obs = {
            "predicate": f["predicate"],
            "value": f.get("value"),
            "valid_until": f.get("valid_until"),
            "document": f["source"]["document"],
            "quote": f["source"]["quote"],
            "url": f"/api/sources/competitors/{f['source']['document']}",
            "trust": f.get("trust", "VERIFIED_PUBLIC"),
        }
        observations.append(obs)

    evidence = [
        {
            "document": f["source"]["document"],
            "quote": f["source"]["quote"],
            "url": f"/api/sources/competitors/{f['source']['document']}",
            "trust": f.get("trust", "VERIFIED_PUBLIC"),
        }
        for f in matching
    ]

    for fact in matching:
        if fact.get("contradicts"):
            derived_facts.append({
                "predicate": requirement_field,
                "claim": fact.get("note", "Public registry record contradicts requirement"),
                "is_supported": False,
            })
            return "PUBLIC NON-MATCH", fact["note"], evidence, observations, derived_facts

        if (
            requirement_field == "certifications"
            and isinstance(fact.get("value"), list)
            and expected in [str(v) for v in fact["value"]]
        ):
            derived_facts.append({
                "predicate": requirement_field,
                "claim": f"Public registry confirms active {expected} certification",
                "is_supported": True,
            })
            return (
                "PUBLICLY SUPPORTED",
                f"Public registry lists {expected} (valid until {fact.get('valid_until', 'stated validity')}).",
                evidence,
                observations,
                derived_facts,
            )

    note = "No public registry record located for this requirement; absence of evidence is not a negative finding."
    return "UNKNOWN", note, evidence, observations, derived_facts


def analyze_requirement_advantage(
    req_id: str,
    req_label: str,
    field: str,
    our_status: str,
    competitor_statuses: list[str],
) -> dict:
    """Evaluates whether a tender requirement offers structural differentiation."""
    total_comps = len(competitor_statuses)
    supported = sum(1 for s in competitor_statuses if s == "PUBLICLY SUPPORTED")
    non_match = sum(1 for s in competitor_statuses if s == "PUBLIC NON-MATCH")
    unknown = sum(1 for s in competitor_statuses if s == "UNKNOWN")

    if our_status == "PASS" and supported == 0:
        advantage = "HIGH ADVANTAGE"
        interpretation = (
            f"Strong differentiator for our company: our verified compliance is established, "
            f"while 0/{total_comps} competitors have public proof."
        )
    elif our_status == "PASS" and supported >= (total_comps / 2):
        advantage = "LOW DIFFERENTIATION"
        interpretation = (
            f"Standard market threshold: widely satisfied by our company and "
            f"{supported}/{total_comps} competitors."
        )
    elif non_match > 0:
        advantage = "MARKET BARRIER"
        interpretation = (
            f"Strict constraint: at least {non_match} competitor(s) have public records of non-compliance."
        )
    elif field == "references" and supported > 0:
        advantage = "INCUMBENT FIELD"
        interpretation = "Public reference records indicate existing public-sector footprint in this category."
    else:
        advantage = "NEUTRAL"
        interpretation = "Standard qualification requirement; competitor public data is partially unobserved."

    return {
        "req_id": req_id,
        "label": req_label,
        "advantage": advantage,
        "interpretation": interpretation,
        "our_status": our_status,
        "competitor_stats": {
            "supported": supported,
            "non_match": non_match,
            "unknown": unknown,
        },
    }


def competitor_landscape(
    requirements: list,
    scope: str,
    deadline: str | None,
    our_checks: list | None = None,
) -> dict:
    """Landscape rows for one tender's mandatory requirements across our company and competitors."""
    data = competitor_data()
    rows = []
    verified_requirements = [
        r for r in requirements if r.mandatory and r.compile_status == "VERIFIED"
    ]

    # Map Our Company's checks if supplied
    our_check_map = {}
    if our_checks:
        our_check_map = {c.requirement.id: c for c in our_checks}

    # 1. OUR COMPANY (Alpine Digital SA) - Pinned as the first row
    our_cells = {}
    for req in verified_requirements:
        check = our_check_map.get(req.id)
        if check:
            status_label = "PUBLICLY SUPPORTED" if check.status == "PASS" else "PUBLIC NON-MATCH" if check.status == "FAIL" else "UNKNOWN"
            our_cells[req.id] = {
                "requirement": req.label,
                "field": req.field,
                "status": status_label,
                "raw_status": check.status,
                "note": f"Internal verified evidence: {check.reason}",
                "evidence": [
                    {
                        "document": check.evidence.source.document,
                        "quote": check.evidence.source.quote,
                        "url": check.evidence.source.url,
                        "trust": check.evidence.trust,
                    }
                ] if check.evidence else [],
                "observations": [],
                "derived_facts": [],
            }
        else:
            our_cells[req.id] = {
                "requirement": req.label,
                "field": req.field,
                "status": "UNKNOWN",
                "raw_status": "UNKNOWN",
                "note": "Awaiting evaluation",
                "evidence": [],
                "observations": [],
                "derived_facts": [],
            }

    rows.append({
        "org": "Alpine Digital SA (Our Company)",
        "org_id": "alpine-digital",
        "registry_id": "CHE-109.845.221",
        "is_us": True,
        "cells": our_cells,
    })

    # 2. COMPETITORS
    for org in data.get("orgs", []):
        cells = {}
        for req in verified_requirements:
            if req.field == "references":
                status, note, evidence, obs, df = _reference_state(
                    org["id"],
                    float(req.expected),
                    req.window_years,
                    deadline,
                    data.get("awards", []),
                    scope,
                )
            else:
                status, note, evidence, obs, df = _registry_state(
                    org["id"], req.field, str(req.expected)
                )

            cells[req.id] = {
                "requirement": req.label,
                "field": req.field,
                "status": status,
                "raw_status": status,
                "note": note,
                "evidence": evidence,
                "observations": obs,
                "derived_facts": df,
            }
        rows.append({
            "org": org["name"],
            "org_id": org["id"],
            "registry_id": org.get("registry_id"),
            "is_us": False,
            "cells": cells,
        })

    # 3. Requirement Advantage / Differentiation Analysis
    req_advantages = {}
    for req in verified_requirements:
        comp_statuses = [
            r["cells"][req.id]["status"]
            for r in rows
            if not r.get("is_us") and req.id in r["cells"]
        ]
        our_st = our_cells.get(req.id, {}).get("raw_status", "UNKNOWN")
        req_advantages[req.id] = analyze_requirement_advantage(
            req.id, req.label, req.field, our_st, comp_statuses
        )

    # 4. Competitor Candidate Generation
    candidates = generate_competitor_candidates(scope, "Demonstration Buyer")

    return {
        "requirements": [
            {
                "id": r.id,
                "label": r.label,
                "field": r.field,
                "advantage": req_advantages.get(r.id, {}).get("advantage", "NEUTRAL"),
                "advantage_note": req_advantages.get(r.id, {}).get("interpretation", ""),
            }
            for r in verified_requirements
        ],
        "orgs": rows,
        "candidates": candidates,
        "advantages": req_advantages,
        "semantics": {
            "PUBLICLY SUPPORTED": "A public record satisfies the compiled rule.",
            "PUBLIC NON-MATCH": "A public record contradicts the compiled rule.",
            "UNKNOWN": "Insufficient public evidence. Never interpreted as inability.",
        },
    }
