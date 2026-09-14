"""Shared fixtures — minimal valid instances of the shared schemas.

Each track can build its own fixtures on top of these; keep these ones
minimal and generic so they stay useful to all three tracks.
"""

from datetime import date

import pytest

from src.schemas.common import Citation, Language
from src.schemas.company import CompanyProfile, Certification, Reference
from src.schemas.tender import (
    AwardCriterion,
    Deadline,
    EligibilityCriterion,
    ExtractedTenderData,
    MandatoryDocument,
)


@pytest.fixture
def sample_citation() -> Citation:
    return Citation(document="cahier_des_charges.pdf", page=3, section="4.2")


@pytest.fixture
def sample_tender(sample_citation: Citation) -> ExtractedTenderData:
    return ExtractedTenderData(
        tender_id="2026-001",
        title="Fourniture de services IT",
        contracting_authority="Ville de Lausanne",
        source_language=Language.FR,
        deadlines=[
            Deadline(label="Submission deadline", date=date(2026, 10, 1), citation=sample_citation)
        ],
        eligibility_criteria=[
            EligibilityCriterion(
                id="elig-1",
                description="ISO 27001 certification",
                category="certification",
                mandatory=True,
                citation=sample_citation,
            )
        ],
        award_criteria=[
            AwardCriterion(id="award-1", description="Price", weight_percent=40.0, citation=sample_citation),
            AwardCriterion(id="award-2", description="Quality", weight_percent=60.0, citation=sample_citation),
        ],
        mandatory_documents=[MandatoryDocument(name="Proof of insurance", citation=sample_citation)],
        source_documents=["notice.pdf", "cahier_des_charges.pdf"],
    )


@pytest.fixture
def sample_company() -> CompanyProfile:
    return CompanyProfile(
        company_name="Acme Consulting SA",
        certifications=[Certification(name="ISO 27001", issuer="SQS")],
        insurance_coverage_chf=2_000_000,
        references=[Reference(client="Canton de Vaud", project_description="IT support", year=2024)],
        annual_revenue_chf=5_000_000,
        employee_count=40,
        languages_supported=[Language.FR, Language.EN],
        capabilities=["IT services", "cybersecurity"],
    )
