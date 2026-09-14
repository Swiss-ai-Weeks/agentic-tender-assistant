"""TODO(track-b): replace with real deterministic eligibility tests once implemented."""

import pytest

from src.agents import eligibility_gate


def test_run_eligibility_gate_not_implemented(sample_tender, sample_company):
    with pytest.raises(NotImplementedError):
        eligibility_gate.run_eligibility_gate(sample_tender, sample_company)
