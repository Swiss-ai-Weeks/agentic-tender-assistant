"""Structured tender data — the output contract of the ingestion agent (Track A)."""

from datetime import date

from pydantic import BaseModel, Field

from src.schemas.common import Citation, Language


class Deadline(BaseModel):
    label: str = Field(..., description="e.g. 'Submission deadline', 'Question deadline'")
    date: date
    citation: Citation


class EligibilityCriterion(BaseModel):
    """Binary pass/fail requirement. Missing one disqualifies the bid outright."""

    id: str
    description: str
    category: str = Field(..., description="e.g. 'certification', 'insurance', 'reference', 'financial'")
    mandatory: bool = True
    citation: Citation


class AwardCriterion(BaseModel):
    """Weighted/scored requirement (price, quality, timeline, sustainability, ...)."""

    id: str
    description: str
    weight_percent: float = Field(..., ge=0, le=100)
    citation: Citation


class MandatoryDocument(BaseModel):
    name: str
    description: str | None = None
    citation: Citation


class ExtractedTenderData(BaseModel):
    """Output of the ingestion & extraction agent for a single tender."""

    tender_id: str | None = None
    title: str
    contracting_authority: str | None = None
    source_language: Language
    deadlines: list[Deadline] = Field(default_factory=list)
    eligibility_criteria: list[EligibilityCriterion] = Field(default_factory=list)
    award_criteria: list[AwardCriterion] = Field(default_factory=list)
    mandatory_documents: list[MandatoryDocument] = Field(default_factory=list)
    source_documents: list[str] = Field(default_factory=list, description="File names processed")
