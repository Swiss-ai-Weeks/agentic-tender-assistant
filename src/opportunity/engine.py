"""Evidence-bound deterministic decisions for the controlled demonstration corpus.

The line grammar is intentionally limited to labelled synthetic fixtures. Live
notices are never assumed to use this grammar or to be fully extracted.
"""
from datetime import date
from pathlib import Path
import json
import re
from urllib.parse import quote

from src.opportunity.models import Check, Evidence, Opportunity, Requirement, Source

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / 'data' / 'demo'


def company_profile():
    return json.loads((DEMO / 'company.json').read_text())


def source_for(path: Path, quote_text: str, line: int | None = None) -> Source:
    source_id = str(path.relative_to(DEMO))
    return Source(id=source_id, document=path.name, quote=quote_text, line=line,
                  url='/api/sources/' + quote(source_id, safe='/'))


def read_evidence(name: str) -> list[Evidence]:
    path = DEMO / 'evidence' / name
    items = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        parts = [x.strip() for x in line.split('|')]
        if len(parts) != 4:
            continue
        field, value, unit, valid_until = parts
        parsed = float(value) if re.fullmatch(r'\d+(?:\.\d+)?', value) else value.split(',')
        items.append(Evidence(field=field, value=parsed, unit=unit,
                              valid_until=valid_until, source=source_for(path, line, n)))
    return items


def evidence_catalog(investigate=False):
    profile = company_profile()
    files = profile['initial_evidence'] + (profile['knowledge_evidence'] if investigate else [])
    return [e for name in files for e in read_evidence(name)]


def evaluate(req: Requirement, evidence: list[Evidence], as_of: date) -> Check:
    action = f'Provide current, verified evidence for {req.label.lower()}.'
    relevant = [e for e in evidence if e.field == req.field]
    valid = []
    for e in relevant:
        try:
            unexpired = date.fromisoformat(e.valid_until) >= as_of
        except ValueError:
            unexpired = False
        # A citation and the matching unit are required; missing data never passes.
        if unexpired and e.source.quote.strip() and e.unit == req.unit:
            valid.append(e)
    if not req.source.quote.strip() or req.operator == 'review':
        return Check(requirement=req, status='UNKNOWN', reason='Human review of this requirement is required.', action=action)
    if not valid:
        return Check(requirement=req, status='UNKNOWN', evidence=relevant[0] if relevant else None,
                     reason='No current evidence with matching units was verified.', action=action)
    if len({json.dumps(e.value, sort_keys=True) for e in valid}) != 1:
        return Check(requirement=req, status='UNKNOWN', reason='Conflicting current evidence; resolve the discrepancy.', action=action)
    e = valid[0]
    if req.operator == '>=':
        if isinstance(e.value, (int, float)) and isinstance(req.expected, (int, float)):
            passed = e.value >= req.expected
        else:
            return Check(requirement=req, status='UNKNOWN', evidence=e,
                         reason='The required numerical comparison could not be verified.', action=action)
    elif req.operator == 'contains' and isinstance(e.value, list) and isinstance(req.expected, str):
        passed = req.expected.casefold() in [v.casefold() for v in e.value]
    else:
        return Check(requirement=req, status='UNKNOWN', evidence=e, reason='Unsupported evidence format.', action=action)
    status = 'PASS' if passed else 'FAIL'
    observed = ', '.join(e.value) if isinstance(e.value, list) else f'{e.value:,.0f}'
    target = f'{req.expected:,.0f}' if isinstance(req.expected, (int, float)) else req.expected
    reason = f'Required: {target} {req.unit}. Verified: {observed} {e.unit}.'
    if req.field == 'insurance':
        action = 'Search for a current insurance certificate. If coverage is insufficient, obtain increased coverage before submission.'
    elif req.field == 'certifications':
        action = f'Obtain {req.expected} certification or verify whether the tender permits an eligible partner.'
    return Check(requirement=req, status=status, evidence=e, reason=reason, action=None if passed else action)


def decide(op: Opportunity, as_of: date) -> Opportunity:
    mandatory = [c for c in op.checks if c.requirement.mandatory]
    op.total = len(mandatory)
    op.verified = sum(c.status == 'PASS' for c in mandatory)
    op.blockers = sum(c.status != 'PASS' for c in mandatory)
    expired = op.deadline is not None and date.fromisoformat(op.deadline) <= as_of
    if any(c.status == 'FAIL' for c in mandatory) or expired:
        op.recommendation = 'NO-GO'
    elif mandatory and op.blockers == 0 and op.complete_documents and op.deadline:
        op.recommendation = 'GO'
    else:
        op.recommendation = 'CONDITIONAL GO' if op.complete_documents else 'UNKNOWN'
    if expired:
        op.risks.append('Submission deadline has passed or falls today; exact closing time must be checked.')
    if not op.complete_documents:
        op.risks.append('Complete tender documentation and eligibility extraction have not been verified. Do not treat this as bid clearance.')
    op.next_steps = [c.action for c in mandatory if c.action]
    op.next_steps += ['Confirm a bid owner and validate the full submission pack.', 'Review pricing and contractual commitments before bidding.']
    return enrich(op)


def extract_demo(path: Path, investigate=False) -> Opportunity:
    lines = path.read_text().splitlines()
    facts = {}
    for n, line in enumerate(lines, 1):
        if ': ' in line and not line.startswith('§'):
            key, value = line.split(': ', 1)
            facts[key] = (value, source_for(path, line, n))
    requirements = []
    for n, line in enumerate(lines, 1):
        if not re.match(r'^R\d+ \|', line):
            continue
        ident, label, field, operator, expected, unit = [p.strip() for p in line.split('|')]
        requirements.append(Requirement(id=ident, label=label, field=field, operator=operator,
                                       expected=float(expected) if operator == '>=' else expected,
                                       unit=unit, source=source_for(path, line, n)))
    profile = company_profile()
    as_of = date.fromisoformat(profile['as_of'])
    text = ' '.join(lines)
    matches = [c for c in profile['capabilities'] if c.casefold() in text.casefold()]
    evidence = evidence_catalog(investigate)
    op = Opportunity(id=path.stem, title=facts['Title'][0], buyer=facts['Buyer'][0],
                     location=facts['Location'][0], deadline=facts['Deadline'][0],
                     summary=facts['Scope'][0], source=facts['Title'][1], mode='demo',
                     facts={k.lower(): v[1] for k, v in facts.items()},
                     contract_value=float(facts['Value'][0].split()[0]) if 'Value' in facts else None,
                     value_currency='CHF' if 'Value' in facts else None,
                     value_basis=facts.get('Value basis', ('Not disclosed',))[0],
                     value_source=facts.get('Value', (None, None))[1],
                     document_count=int(facts['Mandatory document count'][0]) if 'Mandatory document count' in facts else None,
                     complete_documents=facts.get('Complete', ('no',))[0] == 'yes',
                     checks=[evaluate(r, evidence, as_of) for r in requirements],
                     fit_matches=matches,
                     why=[f'Profile capability matched in the scope: {m}.' for m in matches],
                     risks=['Pricing competitiveness has not been evaluated.'],
                     security_events=['Instruction-like text detected in source. Treated as document content; the deterministic eligibility rules are unchanged.'] if 'IGNORE ALL PREVIOUS' in text else [])
    return decide(op, as_of)


FAMILIES = ['Certifications', 'References', 'Financial / Insurance', 'Team', 'Language', 'Geography', 'Security', 'Technical', 'Legal', 'Capacity / Deadline']
FIELD_FAMILY = {'certifications':'Certifications', 'references':'References', 'insurance':'Financial / Insurance', 'revenue':'Financial / Insurance', 'languages':'Language', 'team':'Team', 'geography':'Geography', 'security':'Security', 'technical':'Technical', 'legal':'Legal', 'capacity':'Capacity / Deadline'}


def family_of(check):
    return FIELD_FAMILY.get(check.requirement.field, 'Technical')


def enrich(op):
    for family in FAMILIES:
        statuses = [c.status for c in op.checks if family_of(c) == family]
        op.families[family] = ('FAIL' if 'FAIL' in statuses else 'UNKNOWN' if 'UNKNOWN' in statuses else 'PASS' if statuses else 'N/A')
    assumptions = company_profile()['bid_cost_assumptions']
    if op.document_count is not None and op.complete_documents:
        days = assumptions['base_days'] + op.total * assumptions['days_per_requirement'] + op.blockers * assumptions['days_per_blocker'] + op.document_count * assumptions['days_per_document']
        op.effort_days = [round(days, 1), round(days * assumptions['range_multiplier'], 1)]
        op.bid_cost_chf = [round(d * assumptions['internal_day_rate_chf']) for d in op.effort_days]
        op.effort = 'LOW' if days <= 5 else 'MEDIUM' if days <= 8 else 'HIGH'
        op.effort_explanation = [f"Base {assumptions['base_days']} days + {op.total} requirements × {assumptions['days_per_requirement']} days + {op.blockers} blockers × {assumptions['days_per_blocker']} days + {op.document_count} documents × {assumptions['days_per_document']} days.", f"Range upper bound: × {assumptions['range_multiplier']}; internal day rate CHF {assumptions['internal_day_rate_chf']:,.0f}.", assumptions['model']]
    else:
        op.effort_explanation = ['The full submission document set is unavailable. Bid effort cannot yet be estimated reliably.']
    # Commercial relevance does not change the mandatory eligibility decision.
    op.commercial = 'PROMISING' if op.fit_matches and op.contract_value else 'REVIEW'
    op.priority = 'DO NOT PURSUE' if op.recommendation == 'NO-GO' else 'HIGH' if op.recommendation == 'GO' and op.fit_matches and op.effort in ['LOW', 'MEDIUM'] else 'REVIEW'
    return op


def rank(opportunities):
    order = {'GO': 0, 'CONDITIONAL GO': 1, 'UNKNOWN': 2, 'NO-GO': 3}
    effort = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2, 'NOT ESTIMATED': 3}
    return sorted(opportunities, key=lambda o: (order[o.recommendation], -len(o.fit_matches), effort[o.effort], -(o.contract_value or 0), o.deadline or '9999', o.id))
