"""Track B — Eligibility gate agent.

Deterministic pass/fail check of a tender's eligibility criteria against the
company profile. This step is intentionally rule-based rather than left to
model judgment: missing a mandatory criterion disqualifies the bid outright,
so it should not be subject to probabilistic drift.

TODO(track-b):
- Match each EligibilityCriterion.category (certification, insurance,
  reference, financial, ...) to the relevant CompanyProfile field(s).
- Decide PASS/FAIL/UNKNOWN per criterion (UNKNOWN when the company profile
  doesn't carry enough information to decide — don't force a guess).
- Write a clear justification per criterion referencing the company data used.
"""

from src.schemas.briefing import EligibilityResult
from src.schemas.company import CompanyProfile
from src.schemas.tender import ExtractedTenderData


def run_eligibility_gate(
    tender: ExtractedTenderData, company: CompanyProfile
) -> list[EligibilityResult]:
    """Evaluate every eligibility criterion in `tender` against `company`.

    Returns one EligibilityResult per criterion in `tender.eligibility_criteria`.
    """
    raise NotImplementedError("TODO(track-b): implement deterministic eligibility checks")
