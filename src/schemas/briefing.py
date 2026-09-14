"""Qualification briefing — the final output contract, produced by Track C."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from src.schemas.common import Citation
from src.schemas.tender import AwardCriterion, Deadline, EligibilityCriterion


class EligibilityStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"  # insufficient info in company profile / tender to decide


class EligibilityResult(BaseModel):
    criterion: EligibilityCriterion
    status: EligibilityStatus
    justification: str


class AwardCriterionScore(BaseModel):
    criterion: AwardCriterion
    score: float = Field(..., ge=0, le=100, description="Fit score for this criterion alone")
    weighted_score: float = Field(..., description="score * (weight_percent / 100)")
    justification: str


class RiskFlag(BaseModel):
    severity: Literal["low", "medium", "high"]
    description: str
    citation: Citation | None = None


class GoNoGoRecommendation(str, Enum):
    GO = "go"
    NO_GO = "no_go"
    CONDITIONAL = "conditional"


class QualificationBriefing(BaseModel):
    tender_title: str
    contracting_authority: str | None = None
    deadlines: list[Deadline] = Field(default_factory=list)
    eligibility_results: list[EligibilityResult] = Field(default_factory=list)
    eligibility_gate_passed: bool
    award_criteria_scores: list[AwardCriterionScore] = Field(default_factory=list)
    overall_fit_score: float | None = Field(default=None, description="None if the eligibility gate failed")
    risks: list[RiskFlag] = Field(default_factory=list)
    recommendation: GoNoGoRecommendation
    recommendation_justification: str
    generated_at: datetime
