"""Orchestration entry point — Track C owns this.

Wires: ingestion -> eligibility_gate -> (if pass) fit_scoring -> briefing.

Plain function composition for the skeleton stage — no orchestration
framework dependency yet. See docs/architecture.md "Orchestration" for why,
and for what would need to change to adopt the NVIDIA NeMo Agent Toolkit.

TODO(track-c): nothing structural required here until Track A/B modules are
implemented; this wiring should keep working as-is once they are.
"""

import argparse
from pathlib import Path

from src.agents import briefing, eligibility_gate, fit_scoring, ingestion
from src.schemas.briefing import QualificationBriefing
from src.schemas.company import CompanyProfile


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
