"""Track C — Briefing generation agent.

Produces the final structured qualification briefing: opportunity summary,
deadlines, eligibility status per criterion, award criteria breakdown,
risk/flags, and a go/no-go recommendation with justification.

TODO(track-c):
- Summarize eligibility_results + eligibility_gate_passed into the briefing.
- Fold award_scores into overall_fit_score (only set when gate passed).
- Surface risks (e.g. tight deadlines, UNKNOWN eligibility results, missing
  mandatory documents) as RiskFlags.
- Produce a GoNoGoRecommendation with a written justification grounded in the
  above — no recommendation without a stated reason.
"""

from src.schemas.briefing import AwardCriterionScore, EligibilityResult, QualificationBriefing
from src.schemas.tender import ExtractedTenderData


def generate_briefing(
    tender: ExtractedTenderData,
    eligibility_results: list[EligibilityResult],
    eligibility_gate_passed: bool,
    award_scores: list[AwardCriterionScore],
) -> QualificationBriefing:
    """Assemble the final QualificationBriefing from upstream agent outputs."""
    raise NotImplementedError("TODO(track-c): implement briefing generation")
