"""Orchestration entry point — Track C owns this.

Wires: ingestion -> eligibility_gate -> (if pass) fit_scoring -> briefing.

Two entry points share this one core:
- `run_pipeline()` / `main()`: plain Python, used by `python -m src.pipeline`
  and by the test suite directly.
- The `@register_function`-decorated wrappers below: expose the same four
  agents (plus the end-to-end pipeline) as NVIDIA NeMo Agent Toolkit (`nat`)
  functions, driven by configs/tender_assistant.yml (CLI) and
  configs/tender_assistant_mcp.yml (MCP server for the Hermes sandbox). See
  docs/architecture.md "Orchestration" for why NAT was adopted and why this
  file is the only one that needed to change for it.

TODO(track-c): nothing structural required here until Track A/B modules are
implemented; this wiring should keep working as-is once they are.
"""

import argparse
from pathlib import Path

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from src.agents import briefing, eligibility_gate, fit_scoring, ingestion, tender_search
from src.schemas.briefing import AwardCriterionScore, EligibilityResult, QualificationBriefing
from src.schemas.company import CompanyProfile
from src.schemas.discovery import TenderLead
from src.schemas.tender import ExtractedTenderData


def run_pipeline(tender_folder: Path, company_profile_path: Path) -> QualificationBriefing:
    """Run the full pipeline end-to-end for a single tender."""
    company = CompanyProfile.model_validate_json(company_profile_path.read_text())

    document_paths = sorted(tender_folder.glob("*.pdf"))
    tender_data = ingestion.extract_tender_data(document_paths)

    eligibility_results = eligibility_gate.run_eligibility_gate(tender_data, company)
    gate_passed = all(r.status.value != "fail" for r in eligibility_results)

    award_scores = []
    if gate_passed:
        award_scores = fit_scoring.score_fit(tender_data, company)

    return briefing.generate_briefing(tender_data, eligibility_results, gate_passed, award_scores)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Agentic Tender Assistant pipeline on a single tender."
    )
    parser.add_argument("tender_folder", type=Path, help="Folder containing the tender's PDF documents")
    parser.add_argument("company_profile", type=Path, help="Path to a company profile JSON file")
    parser.add_argument("--out", type=Path, default=None, help="Optional path to write the briefing JSON to")
    args = parser.parse_args()

    result = run_pipeline(args.tender_folder, args.company_profile)
    output = result.model_dump_json(indent=2)

    if args.out:
        args.out.write_text(output)
    else:
        print(output)


if __name__ == "__main__":
    main()


# --- NeMo Agent Toolkit (nat) registration --------------------------------
#
# Each agent is registered individually (so a workflow could call just one,
# e.g. to expose `tender_ingestion` alone to another tool) plus one composite
# `tender_qualification_pipeline` function that mirrors `run_pipeline()`
# above. `name=` on each config is the `_type` used in the YAML configs under
# configs/.


class TenderIngestionConfig(FunctionBaseConfig, name="tender_ingestion"):
    pass


@register_function(config_type=TenderIngestionConfig)
async def tender_ingestion_function(_config: TenderIngestionConfig, _builder: Builder):
    async def _run(document_paths: list[Path]) -> ExtractedTenderData:
        return ingestion.extract_tender_data(document_paths)

    yield FunctionInfo.from_fn(
        _run,
        description="Extract structured, cited tender data (deadlines, eligibility "
        "criteria, award criteria, mandatory documents) from a tender's PDF document set.",
    )


class TenderEligibilityGateConfig(FunctionBaseConfig, name="tender_eligibility_gate"):
    pass


@register_function(config_type=TenderEligibilityGateConfig)
async def tender_eligibility_gate_function(_config: TenderEligibilityGateConfig, _builder: Builder):
    async def _run(tender: ExtractedTenderData, company: CompanyProfile) -> list[EligibilityResult]:
        return eligibility_gate.run_eligibility_gate(tender, company)

    yield FunctionInfo.from_fn(
        _run,
        description="Deterministically pass/fail every eligibility criterion in a tender "
        "against a company profile.",
    )


class TenderFitScoringConfig(FunctionBaseConfig, name="tender_fit_scoring"):
    pass


@register_function(config_type=TenderFitScoringConfig)
async def tender_fit_scoring_function(_config: TenderFitScoringConfig, _builder: Builder):
    async def _run(tender: ExtractedTenderData, company: CompanyProfile) -> list[AwardCriterionScore]:
        return fit_scoring.score_fit(tender, company)

    yield FunctionInfo.from_fn(
        _run,
        description="Score every weighted award criterion in a tender for a company's fit. "
        "Only meaningful once the eligibility gate has passed.",
    )


class TenderBriefingConfig(FunctionBaseConfig, name="tender_briefing"):
    pass


@register_function(config_type=TenderBriefingConfig)
async def tender_briefing_function(_config: TenderBriefingConfig, _builder: Builder):
    async def _run(
        tender: ExtractedTenderData,
        eligibility_results: list[EligibilityResult],
        eligibility_gate_passed: bool,
        award_scores: list[AwardCriterionScore],
    ) -> QualificationBriefing:
        return briefing.generate_briefing(
            tender, eligibility_results, eligibility_gate_passed, award_scores
        )

    yield FunctionInfo.from_fn(
        _run,
        description="Assemble the final structured qualification briefing (go/no-go "
        "recommendation + justification) from upstream agent outputs.",
    )


class TenderQualificationPipelineConfig(FunctionBaseConfig, name="tender_qualification_pipeline"):
    pass


@register_function(config_type=TenderQualificationPipelineConfig)
async def tender_qualification_pipeline_function(
    _config: TenderQualificationPipelineConfig, _builder: Builder
):
    async def _run(tender_folder: Path, company_profile_path: Path) -> QualificationBriefing:
        return run_pipeline(tender_folder, company_profile_path)

    yield FunctionInfo.from_fn(
        _run,
        description="Run the full agentic-tender-assistant pipeline end-to-end for a single "
        "tender folder of PDFs and a company profile, returning a QualificationBriefing.",
    )


class TenderLiveSearchConfig(FunctionBaseConfig, name="tender_live_search"):
    pass


@register_function(config_type=TenderLiveSearchConfig)
async def tender_live_search_function(_config: TenderLiveSearchConfig, _builder: Builder):
    async def _run(query: str, company: CompanyProfile) -> list[TenderLead]:
        return await tender_search.discover_tenders(query, company)

    yield FunctionInfo.from_fn(
        _run,
        description="Discover candidate tenders via a shallow-then-deep Tavily web search "
        "restricted to simap.ch, each lead cited back to the real Tavily result that produced it.",
    )
