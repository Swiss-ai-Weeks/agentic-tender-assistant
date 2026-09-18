import pytest
from pydantic import ValidationError

from src.pipeline import (
    BriefingInput,
    SearchInput,
    WorkflowInput,
    build_briefing,
    run_workflow,
    search_simap,
)


def test_search_normalizes_leads():
    found = search_simap(SearchInput(query="software"))
    assert found
    assert {"id", "publication", "title", "url"} <= found[0].keys()


def test_demo_workflow_is_cited():
    result = run_workflow(WorkflowInput(mode="demo", tender_id="data-platform"))
    assert result["requirements"] and all(x["proof"] for x in result["requirements"])


def test_unknown_cannot_be_go():
    result = run_workflow(WorkflowInput(tender_id="a07bd668-e1c0-4d48-a829-776f14c0e2b2"))
    assert result["mandatory_summary"]["blockers"] > 0 and result["recommendation"] != "GO"


def test_invalid_briefing_rejected():
    with pytest.raises(ValidationError):
        build_briefing(BriefingInput(opportunity={"recommendation": "GO"}))
