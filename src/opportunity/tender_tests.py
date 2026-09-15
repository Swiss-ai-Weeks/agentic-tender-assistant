"""Boundary tests generated from compiled requirements.

Every executable rule yields generated unit tests that exercise the
deterministic evaluator at and around its threshold. A failing generated test
means the engine and the compiled rule disagree — a compilation defect, not an
opinion about the bidder.
"""
from copy import deepcopy
from datetime import date, timedelta

from src.opportunity.models import Evidence, Requirement, Source

TEST_SOURCE = Source(id='generated-test', document='generated-boundary-test', quote='Generated boundary case from the compiled rule.',
                     url='/api/evaluation', trust='SIMULATED')
FAR_FUTURE = '2030-12-31'


def _record(req: Requirement, value, valid_until: str) -> Evidence:
    return Evidence(field=req.field, value=value, unit=req.unit, valid_until=valid_until, source=TEST_SOURCE)


def generate_for(req: Requirement, deadline: str | None) -> list[dict]:
    """Executable, mandatory, verified rules only; everything else stays human work."""
    if req.operator == 'review' or not req.mandatory or req.compile_status != 'VERIFIED':
        return []
    stem = req.field
    cases: list[dict] = []

    def add(ident, kind, given, expected, evidence):
        cases.append({'id': f'test_{stem}_{ident}', 'requirement': req.id, 'kind': kind, 'given': given,
                      'expected': expected, 'evidence': evidence, 'actual': None, 'passed': None})

    if req.operator == '>=':
        target = f'{req.expected:,.0f}'
        below = req.expected - 1 if req.expected >= 1 else req.expected * 0.5
        add('at_threshold', 'boundary', f'{req.field} = {target} {req.unit} → PASS', 'PASS', [_record(req, req.expected, FAR_FUTURE)])
        add('below_threshold', 'boundary', f'{req.field} = {below:,.0f} {req.unit} → FAIL', 'FAIL', [_record(req, below, FAR_FUTURE)])
        add('missing_evidence', 'completeness', f'no {req.field} evidence → UNKNOWN', 'UNKNOWN', [])
        if deadline:
            day_before = (date.fromisoformat(deadline) - timedelta(days=1)).isoformat()
            add('expires_before_deadline', 'validity',
                f'{req.field} = {target} but expires {day_before}, before the {deadline} deadline → FAIL', 'FAIL',
                [_record(req, req.expected, day_before)])
    elif req.operator == 'contains':
        add('present', 'boundary', f"'{req.expected}' listed → PASS", 'PASS', [_record(req, [str(req.expected)], FAR_FUTURE)])
        add('absent', 'boundary', f"'{req.expected}' absent → FAIL", 'FAIL',
            [_record(req, ['not-' + str(req.expected).casefold().replace(' ', '-')], FAR_FUTURE)])
        add('missing_evidence', 'completeness', f'no {req.field} evidence → UNKNOWN', 'UNKNOWN', [])
    return cases


def run_cases(cases: list[dict], requirement: Requirement, evaluate, as_of, deadline: str | None) -> list[dict]:
    for case in cases:
        case['actual'] = evaluate(requirement, case['evidence'], as_of, deadline).status
        case['passed'] = case['actual'] == case['expected']
    return cases
