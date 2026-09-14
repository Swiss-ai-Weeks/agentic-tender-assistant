"""TODO(track-a): replace with real extraction tests once ingestion.py is implemented."""

from pathlib import Path

import pytest

from src.agents import ingestion


def test_extract_tender_data_not_implemented():
    with pytest.raises(NotImplementedError):
        ingestion.extract_tender_data([Path("does_not_exist.pdf")])
