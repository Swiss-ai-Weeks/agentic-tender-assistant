"""TODO(track-c): replace with real briefing generation tests once implemented."""

import pytest

from src.agents import briefing


def test_generate_briefing_not_implemented(sample_tender):
    with pytest.raises(NotImplementedError):
        briefing.generate_briefing(sample_tender, [], True, [])
