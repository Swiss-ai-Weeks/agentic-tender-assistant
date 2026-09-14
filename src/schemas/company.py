"""Company profile — filled in once, reused across tenders (Track B owns the schema)."""

from datetime import date

from pydantic import BaseModel, Field

from src.schemas.common import Language


class Certification(BaseModel):
    name: str
    issuer: str | None = None
    valid_until: date | None = None


class Reference(BaseModel):
    client: str
    project_description: str
    year: int | None = None
    contract_value_chf: float | None = None


class CompanyProfile(BaseModel):
    company_name: str
    certifications: list[Certification] = Field(default_factory=list)
    insurance_coverage_chf: float | None = None
    references: list[Reference] = Field(default_factory=list)
    annual_revenue_chf: float | None = None
    employee_count: int | None = None
    languages_supported: list[Language] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list, description="Free-text capability tags")
    notes: str | None = None
