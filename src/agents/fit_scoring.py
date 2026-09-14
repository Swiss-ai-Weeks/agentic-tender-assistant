"""Track B — Fit scoring agent.

Weighted score of the opportunity against the company profile and award
criteria. Only meant to run once the eligibility gate has passed — see
src/pipeline.py.

TODO(track-b):
- Score each AwardCriterion 0-100 based on company fit (price positioning,
  quality/capability match, timeline feasibility, sustainability, ...).
- Compute weighted_score = score * (criterion.weight_percent / 100).
- Justify each score with a reference to the company data used.
"""

from src.schemas.briefing import AwardCriterionScore
from src.schemas.company import CompanyProfile
from src.schemas.tender import ExtractedTenderData


def score_fit(
    tender: ExtractedTenderData, company: CompanyProfile
) -> list[AwardCriterionScore]:
    """Score every award criterion in `tender` for `company`'s fit.

    Returns one AwardCriterionScore per criterion in `tender.award_criteria`.
    Should only be called once the eligibility gate has passed.
    """
    raise NotImplementedError("TODO(track-b): implement weighted fit scoring")
