"""Track A — Ingestion & extraction agent.

Parses a tender's document set (notice, cahier des charges, annexes — any of
FR/DE/IT) and extracts structured fields: deadlines, eligibility criteria,
award criteria + weights, mandatory documents to submit. Every extracted
field must carry a Citation back to its source document (see
src/schemas/common.py).

TODO(track-a):
- Choose a PDF parsing approach (page-level text extraction, keep page
  numbers for citations).
- Chunk documents in a way that preserves page/section boundaries.
- LLM-based structured extraction into ExtractedTenderData, with citations
  attached at extraction time (not backfilled afterwards).
- Handle FR/DE/IT source documents.
"""

from pathlib import Path

from src.schemas.tender import ExtractedTenderData


def extract_tender_data(document_paths: list[Path]) -> ExtractedTenderData:
    """Extract structured, cited tender data from a tender's document set.

    Args:
        document_paths: paths to the tender's PDFs (notice, cahier des
            charges, annexes, ...).

    Returns:
        ExtractedTenderData with every field traceable to a source document.
    """
    raise NotImplementedError("TODO(track-a): implement extraction pipeline")
