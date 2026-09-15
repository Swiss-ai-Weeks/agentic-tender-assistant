"""Typed product contracts. A decision always travels with its evidence."""
from typing import Literal
from pydantic import BaseModel, Field

Status = Literal['PASS', 'FAIL', 'UNKNOWN']
CompileStatus = Literal['VERIFIED', 'NEEDS_REVIEW', 'AMBIGUOUS', 'UNSUPPORTED']
Trust = Literal['VERIFIED_INTERNAL', 'VERIFIED_PUBLIC', 'INFERRED', 'SIMULATED']
CompetitorStatus = Literal['PUBLICLY SUPPORTED', 'PUBLIC NON-MATCH', 'UNKNOWN']
Remediation = Literal['FIND EVIDENCE', 'PARTNER OR SUBCONTRACT', 'ACQUIRE CAPABILITY', 'HUMAN REVIEW']

class Source(BaseModel):
    id: str
    document: str
    quote: str
    line: int | None = None
    page: int | None = None
    section: str | None = None
    url: str
    trust: Trust = 'VERIFIED_INTERNAL'
    retrieved_at: str | None = None
    sha256: str | None = None

class Requirement(BaseModel):
    id: str
    label: str
    field: str
    operator: Literal['>=', 'contains', 'review']
    expected: float | str
    unit: str = ''
    mandatory: bool = True
    source: Source
    raw_clause: str | None = None
    compile_status: CompileStatus | None = None
    compile_reason: str | None = None
    window_years: int | None = None

class Evidence(BaseModel):
    field: str
    value: float | str | list[str]
    unit: str = ''
    valid_until: str
    source: Source
    trust: Trust = 'VERIFIED_INTERNAL'
    valid_from: str | None = None
    observed_at: str | None = None

class ProofStep(BaseModel):
    stage: Literal['CLAUSE', 'RULE', 'FACT', 'EVIDENCE', 'VERDICT']
    text: str
    ref: str | None = None

class Check(BaseModel):
    requirement: Requirement
    status: Status
    evidence: Evidence | None = None
    reason: str
    action: str | None = None
    proof: list[ProofStep] = Field(default_factory=list)
    simulated: bool = False
    remediation: Remediation | None = None
    deadline_feasible: bool | None = None

class Opportunity(BaseModel):
    id: str
    title: str
    buyer: str
    location: str
    deadline: str | None = None
    summary: str
    mode: Literal['demo', 'live', 'captured']
    source: Source
    facts: dict[str, Source] = Field(default_factory=dict)
    checks: list[Check] = Field(default_factory=list)
    recommendation: Literal['GO', 'CONDITIONAL GO', 'UNKNOWN', 'NO-GO'] = 'CONDITIONAL GO'
    verified: int = 0
    total: int = 0
    blockers: int = 0
    why: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    fit_matches: list[str] = Field(default_factory=list)
    security_events: list[str] = Field(default_factory=list)
    complete_documents: bool = False
    contract_value: float | None = None
    value_currency: str | None = None
    value_basis: str | None = None
    value_source: Source | None = None
    tender_version: int | None = None
    retrieved_at: str | None = None
    sha256: str | None = None
    compiled_total: int = 0
    compiled_executable: int = 0
    compiled_review: int = 0
    tests_generated: int = 0
    tests_passed: int = 0
    blocking_set: list[str] = Field(default_factory=list)
    needs_review: list[str] = Field(default_factory=list)
    document_count: int | None = None
    families: dict[str, Status | Literal['N/A']] = Field(default_factory=dict)
    effort: str = 'NOT ESTIMATED'
    effort_days: list[float] = Field(default_factory=list)
    bid_cost_chf: list[float] = Field(default_factory=list)
    effort_explanation: list[str] = Field(default_factory=list)
    priority: str = 'REVIEW'
    commercial: str = 'UNASSESSED'

class Event(BaseModel):
    at: str
    stage: str
    message: str

class Run(BaseModel):
    id: str
    mode: Literal['demo', 'live', 'captured']
    status: Literal['running', 'complete', 'error'] = 'running'
    events: list[Event] = Field(default_factory=list)
    opportunities: list[Opportunity] = Field(default_factory=list)
    discovered: int = 0
    relevant: int = 0
    investigated: int = 0
    elapsed_seconds: float = 0
    error: str | None = None
    searched_evidence: bool = False
    profile_version: str = ''
    rule_compiler_version: str = ''
    engine_version: str = ''
