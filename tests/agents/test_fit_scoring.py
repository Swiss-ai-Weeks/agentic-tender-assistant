"""TODO(track-b): replace with real scoring tests once fit_scoring.py is implemented."""

import pytest

from src.agents import fit_scoring


def test_score_fit_not_implemented(sample_tender, sample_company):
    with pytest.raises(NotImplementedError):
        fit_scoring.score_fit(sample_tender, sample_company)
