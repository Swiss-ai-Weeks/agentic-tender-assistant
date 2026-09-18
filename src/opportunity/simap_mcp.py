"""Typed, read-only boundary for the SIMAP MCP tools used by the MVP.

Hermes and NeMo Agent Toolkit can supply any transport implementing ``MCPTransport``.
The local subprocess transport is retained for development; tests use fixtures and
therefore never require SIMAP, Node, Hermes, or network access.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

ToolName = Literal["search_tenders", "get_tender_details", "list_cantons"]
ALLOWED_TOOLS: frozenset[str] = frozenset(
    {"search_tenders", "get_tender_details", "list_cantons"}
)


class SimapError(RuntimeError):
    """Base error for a failed or malformed SIMAP MCP call."""


class SimapTransportError(SimapError):
    """The configured MCP transport could not complete the call."""


class SimapResponseError(SimapError):
    """The MCP server returned an error or an unsupported response shape."""


class MCPTransport(Protocol):
    """Minimal injection point for Hermes, NAT, HTTP, stdio, or fixture transports."""

    def call(self, tool: ToolName, arguments: Mapping[str, Any]) -> Mapping[str, Any]: ...


class SearchTendersRequest(BaseModel):
    search: str = Field(min_length=1)
    pub_types: list[str] = Field(default_factory=lambda: ["tender"])
    lang: str = "en"
    date_from: str | None = None
    last_item: str | None = None

    def tool_arguments(self) -> dict[str, Any]:
        values: dict[str, Any] = {
            "search": self.search,
            "pubTypes": self.pub_types,
            "lang": self.lang,
        }
        if self.date_from:
            values["dateFrom"] = self.date_from
        if self.last_item:
            values["lastItem"] = self.last_item
        return values


class TenderDetailsRequest(BaseModel):
    project_id: str = Field(min_length=1)
    publication_id: str = Field(min_length=1)
    lang: str = "en"
    full_raw: bool = True

    def tool_arguments(self) -> dict[str, Any]:
        return {
            "projectId": self.project_id,
            "publicationId": self.publication_id,
            "lang": self.lang,
            "fullRaw": self.full_raw,
        }


class TenderLead(BaseModel):
    project_id: str
    publication_id: str
    title: str
    buyer: str = "Not disclosed"
    location: str = "Not disclosed"
    url: str | None = None
    publication_date: str | None = None
    procurement_type: str | None = None
    process: str | None = None
    source_text: str = ""

    def legacy_dict(self) -> dict[str, Any]:
        """Compatibility shape for the existing opportunity compiler."""
        return {
            "id": self.project_id,
            "publication": self.publication_id,
            "title": self.title,
            "buyer": self.buyer,
            "location": self.location,
            "url": self.url,
            "text": self.source_text,
        }


class SearchTendersResult(BaseModel):
    tenders: list[TenderLead] = Field(default_factory=list)
    next_cursor: str | None = None


class TenderDetails(BaseModel):
    project_id: str
    publication_id: str
    raw_notice: dict[str, Any]
    response_text: str


def content_text(payload: Mapping[str, Any]) -> str:
    if payload.get("isError"):
        raise SimapResponseError("SIMAP MCP returned a tool error")
    content = payload.get("content")
    if not isinstance(content, list):
        raise SimapResponseError("SIMAP MCP response has no content list")
    chunks = [
        item.get("text", "")
        for item in content
        if isinstance(item, Mapping) and item.get("type") == "text"
    ]
    if not chunks:
        raise SimapResponseError("SIMAP MCP response has no text content")
    return "\n".join(chunks)


def parse_search_response(payload: Mapping[str, Any]) -> SearchTendersResult:
    text = content_text(payload)
    tenders: list[TenderLead] = []
    for block in re.split(r"\n## ", text)[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        fields = dict(re.findall(r"^- \*\*([^*]+):\*\*\s*(.*)$", block, re.MULTILINE))
        project_id = fields.get("Project ID")
        publication_id = fields.get("Publication ID")
        if not project_id or not publication_id:
            continue
        tenders.append(
            TenderLead(
                project_id=project_id,
                publication_id=publication_id,
                title=lines[0].strip(),
                buyer=fields.get("Office") or "Not disclosed",
                location=fields.get("Location") or "Not disclosed",
                url=fields.get("simap Link") or None,
                publication_date=fields.get("Publication Date") or None,
                procurement_type=fields.get("Type") or None,
                process=fields.get("Process") or None,
                source_text=block,
            )
        )
    cursor_match = re.search(r'Use lastItem:\s*"([^"]+)"', text)
    return SearchTendersResult(
        tenders=tenders,
        next_cursor=cursor_match.group(1) if cursor_match else None,
    )


def parse_details_response(payload: Mapping[str, Any]) -> TenderDetails:
    text = content_text(payload)
    match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    if not match:
        raise SimapResponseError("SIMAP details response has no full raw JSON notice")
    try:
        raw = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise SimapResponseError("SIMAP details response contains invalid JSON") from exc
    if not isinstance(raw, dict):
        raise SimapResponseError("SIMAP raw notice is not an object")
    base = raw.get("base") if isinstance(raw.get("base"), dict) else {}
    project_id = base.get("projectId")
    publication_id = base.get("id") or raw.get("id")
    if not isinstance(project_id, str) or not isinstance(publication_id, str):
        raise SimapResponseError("SIMAP raw notice is missing project/publication identifiers")
    return TenderDetails(
        project_id=project_id,
        publication_id=publication_id,
        raw_notice=raw,
        response_text=text,
    )


class SimapMCPClient:
    """Typed facade over the three approved read-only SIMAP tools."""

    def __init__(self, transport: MCPTransport):
        self.transport = transport

    def search_tenders(self, request: SearchTendersRequest) -> SearchTendersResult:
        return parse_search_response(
            self.transport.call("search_tenders", request.tool_arguments())
        )

    def get_tender_details(self, request: TenderDetailsRequest) -> TenderDetails:
        details = parse_details_response(
            self.transport.call("get_tender_details", request.tool_arguments())
        )
        if details.project_id != request.project_id:
            raise SimapResponseError("SIMAP response project id does not match the request")
        if details.publication_id != request.publication_id:
            raise SimapResponseError("SIMAP response publication id does not match the request")
        return details


class SubprocessMCPTransport:
    """Local development transport through the existing allow-listed Node bridge."""

    def __init__(self, bridge: Path, *, timeout_seconds: int = 60):
        self.bridge = bridge
        self.timeout_seconds = timeout_seconds

    def call(self, tool: ToolName, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        if tool not in ALLOWED_TOOLS:
            raise SimapTransportError(f"SIMAP tool is not allowed: {tool}")
        try:
            result = subprocess.run(
                ["node", str(self.bridge), tool, json.dumps(dict(arguments))],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SimapTransportError("SIMAP MCP transport is unavailable") from exc
        if result.returncode:
            raise SimapTransportError("SIMAP MCP transport is unavailable")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise SimapTransportError("SIMAP MCP transport returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise SimapTransportError("SIMAP MCP transport returned a non-object payload")
        return payload


def localized_text(value: Any) -> str:
    """Small shared helper for consumers of typed raw notices."""
    if isinstance(value, Mapping):
        return next(
            (str(value[key]) for key in ("en", "fr", "de", "it") if value.get(key)),
            "",
        )
    return value if isinstance(value, str) else ""


def plain_text(value: Any) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", localized_text(value))).strip()
