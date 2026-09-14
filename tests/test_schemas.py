"""Schema round-trip tests — these are the shared contracts every track builds against.

TODO: extend as schemas evolve; keep these in sync with src/schemas/.
"""

from datetime import datetime

from src.schemas.briefing import GoNoGoRecommendation, QualificationBriefing


def test_extracted_tender_data_round_trip(sample_tender):
    restored = sample_tender.model_validate_json(sample_tender.model_dump_json())
    assert restored == sample_tender


def test_company_profile_round_trip(sample_company):
    restored = sample_company.model_validate_json(sample_company.model_dump_json())
    assert restored == sample_company


def test_qualification_briefing_minimal(sample_tender):
    result = QualificationBriefing(
        tender_title=sample_tender.title,
        contracting_authority=sample_tender.contracting_authority,
        deadlines=sample_tender.deadlines,
        eligibility_results=[],
        eligibility_gate_passed=True,
        award_criteria_scores=[],
        overall_fit_score=None,
        risks=[],
        recommendation=GoNoGoRecommendation.GO,
        recommendation_justification="Example justification.",
        generated_at=datetime.now(),
    )
    assert result.eligibility_gate_passed is True
