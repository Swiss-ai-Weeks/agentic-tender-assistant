"""Live tender-discovery lead — output contract of src/agents/tender_search.py.

Deliberately lighter-weight than ExtractedTenderData: a discovery-stage lead
worth investigating further, not a fully cited requirements extraction. Each
lead still carries one Citation back to what produced it.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from src.schemas.common import Citation


class TenderLead(BaseModel):
    """A candidate tender surfaced by live web/research search, not yet ingested."""

    title: str
    url: str = Field(..., description="Where this lead points — a source URL or backend identifier")
    contracting_authority: str | None = None
    summary: str
    relevance_note: str | None = Field(
        default=None, description="Why this looks relevant to the company, if available"
    )
    citation: Citation
    found_at: datetime
