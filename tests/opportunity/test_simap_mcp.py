import json
from pathlib import Path

import pytest

from src.opportunity.simap_mcp import (
    SearchTendersRequest,
    SimapMCPClient,
    SimapResponseError,
    TenderDetailsRequest,
    parse_details_response,
    parse_search_response,
)

CAPTURED = Path(__file__).resolve().parents[2] / "data" / "captured"


class FixtureTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def call(self, tool, arguments):
        self.calls.append((tool, dict(arguments)))
        return self.responses[tool]


def fixture(name):
    return json.loads((CAPTURED / name).read_text(encoding="utf-8"))


def test_search_fixture_is_parsed_into_typed_leads_and_cursor():
    result = parse_search_response(fixture("search-software.json"))
    atlassian = next(t for t in result.tenders if t.title == "Atlassian Cloud 2026")
    assert atlassian.project_id == "b1bd13b4-ec34-4786-814e-1680a39e03c2"
    assert atlassian.publication_id == "e37b5c78-8d7e-4279-8163-036e4a82d5b4"
    assert atlassian.buyer == "Stadt Zürich, Organisation und Informatik (OIZ)"
    assert atlassian.url == "https://www.simap.ch/en/project-detail/" + atlassian.project_id
    assert result.next_cursor == "20260901|43242"


def test_details_fixture_exposes_raw_notice_with_matching_ids():
    details = parse_details_response(
        fixture("b1bd13b4-ec34-4786-814e-1680a39e03c2.json")
    )
    assert details.project_id == "b1bd13b4-ec34-4786-814e-1680a39e03c2"
    assert details.publication_id == "e37b5c78-8d7e-4279-8163-036e4a82d5b4"
    assert details.raw_notice["dates"]["offerDeadline"].startswith("2026-10-21")


def test_client_maps_typed_requests_to_existing_mcp_argument_names():
    search_payload = fixture("search-software.json")
    details_payload = fixture("b1bd13b4-ec34-4786-814e-1680a39e03c2.json")
    transport = FixtureTransport(
        {"search_tenders": search_payload, "get_tender_details": details_payload}
    )
    client = SimapMCPClient(transport)
    result = client.search_tenders(
        SearchTendersRequest(search="software", date_from="2026-09-01")
    )
    lead = next(t for t in result.tenders if t.title == "Atlassian Cloud 2026")
    client.get_tender_details(
        TenderDetailsRequest(
            project_id=lead.project_id, publication_id=lead.publication_id
        )
    )
    assert transport.calls == [
        (
            "search_tenders",
            {
                "search": "software",
                "pubTypes": ["tender"],
                "lang": "en",
                "dateFrom": "2026-09-01",
            },
        ),
        (
            "get_tender_details",
            {
                "projectId": lead.project_id,
                "publicationId": lead.publication_id,
                "lang": "en",
                "fullRaw": True,
            },
        ),
    ]


def test_client_rejects_mismatched_detail_response():
    transport = FixtureTransport(
        {
            "get_tender_details": fixture(
                "b1bd13b4-ec34-4786-814e-1680a39e03c2.json"
            )
        }
    )
    client = SimapMCPClient(transport)
    with pytest.raises(SimapResponseError, match="project id"):
        client.get_tender_details(
            TenderDetailsRequest(project_id="wrong", publication_id="also-wrong")
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"isError": True, "content": []},
        {"content": []},
        {"content": [{"type": "text", "text": "no raw JSON"}]},
    ],
)
def test_malformed_details_fail_closed(payload):
    with pytest.raises(SimapResponseError):
        parse_details_response(payload)
