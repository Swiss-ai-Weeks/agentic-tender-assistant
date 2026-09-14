"""Shared primitives used across the tender/company/briefing schemas."""

from enum import Enum

from pydantic import BaseModel, Field


class Language(str, Enum):
    FR = "fr"
    DE = "de"
    IT = "it"
    EN = "en"


class Citation(BaseModel):
    """Traceability back to the source document for an extracted fact.

    Every fact pulled out of a tender document (deadline, criterion,
    requirement, ...) must carry one of these. Never assert a fact without it.
    """

    document: str = Field(..., description="Source file name, e.g. 'cahier_des_charges.pdf'")
    page: int | None = Field(default=None, description="Page number, 1-indexed, if known")
    section: str | None = Field(default=None, description="Section/clause reference, e.g. '4.2'")
    quote: str | None = Field(default=None, description="Optional exact snippet supporting the fact")
