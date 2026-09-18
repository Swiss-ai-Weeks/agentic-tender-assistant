"""Minimal NeMo Agent Toolkit workflow for tender qualification."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig
from pydantic import BaseModel, Field

from src.opportunity.engine import DEMO, decide, extract_demo
from src.opportunity.models import Opportunity
from src.opportunity.simap import CAPTURED, mcp_call, notice_opportunity, relevant
from src.opportunity.simap_mcp import (
    MCPTransport,
    SearchTendersRequest,
    SimapMCPClient,
    TenderDetailsRequest,
    parse_details_response,
    parse_search_response,
)


class HermesSimapTransport(MCPTransport):
    """Runtime boundary for the SIMAP MCP exposed to Hermes/NAT."""

    def call(self, tool, arguments):
        return mcp_call(tool, dict(arguments))


def simap_client() -> SimapMCPClient:
    return SimapMCPClient(HermesSimapTransport())


class SearchInput(BaseModel):
    query: str = Field(min_length=1)
    mode: Literal["live", "captured"] = "captured"
    publication_from: str | None = None


class LoadTenderInput(BaseModel):
    lead: dict[str, Any]
    mode: Literal["live", "captured"] = "captured"


class QualifyInput(BaseModel):
    opportunity: dict[str, Any]
    as_of: str | None = None


class BriefingInput(BaseModel):
    opportunity: dict[str, Any]


class WorkflowInput(BaseModel):
    query: str = "software"
    mode: Literal["live", "captured", "demo"] = "captured"
    tender_id: str | None = None
    as_of: str | None = None


def search_simap(request: SearchInput) -> list[dict[str, Any]]:
    if request.mode == "live":
        result = simap_client().search_tenders(
            SearchTendersRequest(
                search=request.query,
                date_from=request.publication_from
                or (datetime.now(UTC).date() - timedelta(days=30)).isoformat(),
            )
        )
    else:
        payload = json.loads((CAPTURED / "search-software.json").read_text())
        result = parse_search_response(payload)
    query = request.query.casefold()
    found = [x.legacy_dict() for x in result.tenders]
    found = [x for x in found if query in x["text"].casefold() or relevant(x)]
    return sorted(found, key=lambda x: (query not in x["text"].casefold(), x["title"]))


def load_tender(request: LoadTenderInput) -> Opportunity:
    lead = request.lead
    if request.mode == "live":
        details = simap_client().get_tender_details(
            TenderDetailsRequest(
                project_id=lead["id"], publication_id=lead["publication"]
            )
        )
        payload = details.raw_notice
        source_id = f"simap/{lead['id']}"
    else:
        path = CAPTURED / f"{lead['id']}.json"
        if not path.is_file():
            raise ValueError(f"No captured notice for {lead['id']}")
        details = parse_details_response(json.loads(path.read_text()))
        payload, source_id = details.raw_notice, f"captured/{path.name}"
    return notice_opportunity(lead, payload, source_id, request.mode)


def qualify_tender(request: QualifyInput) -> Opportunity:
    as_of = date.fromisoformat(request.as_of) if request.as_of else datetime.now(UTC).date()
    return decide(Opportunity.model_validate(request.opportunity), as_of)


def build_briefing(request: BriefingInput) -> dict[str, Any]:
    op = Opportunity.model_validate(request.opportunity)
    return {
        "tender": {
            "id": op.id,
            "title": op.title,
            "buyer": op.buyer,
            "location": op.location,
            "deadline": op.deadline,
            "summary": op.summary,
            "source": op.source.model_dump(mode="json"),
        },
        "recommendation": op.recommendation,
        "mandatory_summary": {"verified": op.verified, "total": op.total, "blockers": op.blockers},
        "requirements": [x.model_dump(mode="json") for x in op.checks],
        "risks": op.risks,
        "next_steps": op.next_steps,
        "needs_review": op.needs_review,
        "safety_note": "UNKNOWN requirements are blockers; this briefing is not bid clearance.",
    }


def run_workflow(request: WorkflowInput) -> dict[str, Any]:
    if request.mode == "demo":
        op = extract_demo(DEMO / "tenders" / f"{request.tender_id or 'data-platform'}.txt")
    else:
        found = search_simap(SearchInput(query=request.query, mode=request.mode))
        if request.tender_id:
            found = [x for x in found if x["id"] == request.tender_id]
        if not found:
            raise ValueError("No matching tender was found")
        op = load_tender(LoadTenderInput(lead=found[0], mode=request.mode))
    op = qualify_tender(QualifyInput(opportunity=op.model_dump(mode="json"), as_of=request.as_of))
    return build_briefing(BriefingInput(opportunity=op.model_dump(mode="json")))


class SearchConfig(FunctionBaseConfig, name="search_simap"):
    pass


@register_function(config_type=SearchConfig)
async def register_search(c: SearchConfig, b: Builder):
    async def run(request: SearchInput) -> list[dict[str, Any]]:
        return search_simap(request)

    yield FunctionInfo.from_fn(run, input_schema=SearchInput, description="Search SIMAP tenders.")


class LoadConfig(FunctionBaseConfig, name="load_tender"):
    pass


@register_function(config_type=LoadConfig)
async def register_load(c: LoadConfig, b: Builder):
    async def run(request: LoadTenderInput) -> dict[str, Any]:
        return load_tender(request).model_dump(mode="json")

    yield FunctionInfo.from_fn(
        run, input_schema=LoadTenderInput, description="Load a SIMAP notice."
    )


class QualifyConfig(FunctionBaseConfig, name="qualify_tender"):
    pass


@register_function(config_type=QualifyConfig)
async def register_qualify(c: QualifyConfig, b: Builder):
    async def run(request: QualifyInput) -> dict[str, Any]:
        return qualify_tender(request).model_dump(mode="json")

    yield FunctionInfo.from_fn(
        run, input_schema=QualifyInput, description="Apply deterministic eligibility rules."
    )


class BriefingConfig(FunctionBaseConfig, name="build_briefing"):
    pass


@register_function(config_type=BriefingConfig)
async def register_briefing(c: BriefingConfig, b: Builder):
    async def run(request: BriefingInput) -> dict[str, Any]:
        return build_briefing(request)

    yield FunctionInfo.from_fn(
        run, input_schema=BriefingInput, description="Build a cited qualification briefing."
    )


class WorkflowConfig(FunctionBaseConfig, name="tender_qualification_workflow"):
    pass


@register_function(config_type=WorkflowConfig)
async def register_workflow(c: WorkflowConfig, b: Builder):
    async def run(request: str) -> str:
        """Console/MCP frontends pass their payload as a JSON string."""
        parsed = WorkflowInput.model_validate_json(request)
        return json.dumps(run_workflow(parsed), ensure_ascii=False)

    yield FunctionInfo.from_fn(
        run, description="Run the fixed tender MVP workflow from a JSON request."
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--query", default="software")
    p.add_argument("--mode", choices=["live", "captured", "demo"], default="captured")
    p.add_argument("--tender-id")
    p.add_argument("--as-of")
    print(
        json.dumps(
            run_workflow(WorkflowInput(**vars(p.parse_args()))), ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
