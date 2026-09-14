"""Mocks the Tavily API over HTTP — no real network calls in tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents import tender_search


def _response(json_body: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_body)
    return resp


def _mock_client(*post_responses: MagicMock) -> AsyncMock:
    client = AsyncMock()
    client.post.side_effect = list(post_responses)
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    return client


async def test_discover_tenders_runs_shallow_then_deep(sample_company, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")

    shallow = _response(
        {"results": [{"title": "Tender A", "url": "https://simap.ch/a", "content": "IT services tender."}]}
    )
    deep = _response(
        {"results": [{"title": "Tender A detail", "url": "https://simap.ch/a", "content": "Deep dive on tender A."}]}
    )
    mock_client = _mock_client(shallow, deep)

    with patch("src.agents.tender_search.httpx.AsyncClient", return_value=mock_client):
        leads = await tender_search.discover_tenders("fourniture informatique Lausanne", sample_company)

    assert len(leads) == 2
    assert leads[0].relevance_note is None
    assert leads[1].relevance_note is not None
    assert all(lead.citation.document == "https://simap.ch/a" for lead in leads)

    shallow_call, deep_call = mock_client.post.call_args_list
    assert shallow_call.kwargs["json"]["search_depth"] == "basic"
    assert deep_call.kwargs["json"]["search_depth"] == "advanced"
    assert shallow_call.kwargs["json"]["include_domains"] == tender_search.SIMAP_DOMAINS


async def test_discover_tenders_requires_api_key(sample_company, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
        await tender_search.discover_tenders("fourniture informatique Lausanne", sample_company)
