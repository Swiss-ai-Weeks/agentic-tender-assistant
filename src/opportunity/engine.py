"""Evidence-bound deterministic qualification for the controlled corpus.

Clauses are compiled by the Tender Compiler; the decision is evaluated by this
deterministic engine. Validity is judged against the submission deadline, not
merely today. Every result carries a proof chain: clause → rule → fact →
evidence → verdict.
"""
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from src.opportunity.compiler import compile_clause
from src.opportunity.facts import company_facts, file_source
from src.opportunity.models import Check, Evidence, Opportunity, ProofStep, Requirement, Source
from src.opportunity.tender_tests import generate_for, run_cases

ENGINE_VERSION = 'engine/0.4.1'
ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / 'data' / 'demo'

# Stated planning assumptions for deadline feasibility, not measured lead times.
LEAD_TIME_DAYS = {'certifications': 120, 'languages': 90, 'insurance': 20, 'references': 45,
                  'revenue': 180, 'team': 60, 'technical': 45, 'legal': 30, 'geography': 30, 'security': 45}
FIND_EVIDENCE_DAYS = 7


def company_profile():
    return json.loads((DEMO / 'company.json').read_text())


def source_for(path: Path, quote_text: str, line: int | None = None) -> Source:
    return file_source(path, quote_text, line)


def evidence_catalog(investigate=False):
    profile = company_profile()
    files = profile['initial_evidence'] + (profile['knowledge_evidence'] if investigate else [])
    return company_facts(files)


def rule_text(req: Requirement) -> str:
    if req.operator == 'review':
        return 'HUMAN REVIEW · not compiled into an executable rule'
    target = f'{req.expected:,.0f}' if isinstance(req.expected, (int, float)) else f"'{req.expected}'"
    window = f' · window {req.window_years}y' if req.window_years else ''
    return f'{req.field} {req.operator} {target} {req.unit} · {"MANDATORY" if req.mandatory else "NON-BINDING"}{window}'


def format_value(value) -> str:
    if isinstance(value, list):
        return ', '.join(str(v) for v in value)
    if isinstance(value, (int, float)):
        return f'{value:,.0f}'
    return str(value)


def proof_chain(req: Requirement, evidence: Evidence | None, status: str, reason: str) -> list[ProofStep]:
    steps = [ProofStep(stage='CLAUSE', text=req.raw_clause or req.source.quote, ref=req.source.url),
             ProofStep(stage='RULE', text=f'{req.id}: {rule_text(req)} · compiled {req.compile_status or "UNSUPPORTED"}')]
    if evidence is not None:
        steps.append(ProofStep(stage='FACT', text=f'Company fact {req.field} = {format_value(evidence.value)}'
                               + f' {evidence.unit} · {evidence.trust} · valid until {evidence.valid_until}'))
        steps.append(ProofStep(stage='EVIDENCE', text=f'{evidence.source.document}'
                               + (f' line {evidence.source.line}' if evidence.source.line else '')
                               + f': "{evidence.source.quote}"', ref=evidence.source.url))
    else:
        steps.append(ProofStep(stage='FACT', text=f'No verified company fact for predicate "{req.field}".'))
    steps.append(ProofStep(stage='VERDICT', text=f'{status} — {reason}'))
    return steps


def evaluate(req: Requirement, evidence: list[Evidence], as_of: date, deadline: str | None = None) -> Check:
    action = f'Provide current, verified evidence for {req.label.lower()}.'
    done = lambda status, reason, ev=None, act=action: Check(requirement=req, status=status, evidence=ev,
                                                             reason=reason, action=None if status == 'PASS' else act,
                                                             proof=proof_chain(req, ev, status, reason))
    if not req.source.quote.strip() or req.operator == 'review':
        return done('UNKNOWN', 'Human review of this requirement is required.')
    relevant = [e for e in evidence if e.field == req.field]
    current = []
    for e in relevant:
        try:
            valid_until = date.fromisoformat(e.valid_until)
        except ValueError:
            continue  # an unverifiable validity date can never pass
        # A citation, the matching unit and current validity are all required.
        if valid_until >= as_of and e.source.quote.strip() and e.unit == req.unit:
            current.append(e)
    if not current:
        return done('UNKNOWN', 'No current evidence with matching units was verified.')
    if req.operator == '>=':
        if len({json.dumps(e.value, sort_keys=True) for e in current}) != 1:
            return done('UNKNOWN', 'Conflicting current evidence; resolve the discrepancy.')
        best = max(current, key=lambda e: e.value if isinstance(e.value, (int, float)) else 0)
        if not (isinstance(best.value, (int, float)) and isinstance(req.expected, (int, float))):
            return done('UNKNOWN', 'The required numerical comparison could not be verified.', best)
        threshold_met = best.value >= req.expected
        observed = f'{best.value:,.0f}'
    elif req.operator == 'contains':
        if not any(isinstance(e.value, list) for e in current):
            return done('UNKNOWN', 'Unsupported evidence format.', current[0])
        # Registers are unioned: any current record that lists the item supports it.
        matching = [e for e in current if isinstance(e.value, list) and req.expected.casefold() in [v.casefold() for v in e.value]]
        best = matching[0] if matching else current[0]
        threshold_met = bool(matching)
        observed = format_value(best.value)
    else:
        return done('UNKNOWN', 'Unsupported evidence format.', current[0])
    expiry_failure = deadline is not None and date.fromisoformat(best.valid_until) < date.fromisoformat(deadline)
    target = f'{req.expected:,.0f}' if isinstance(req.expected, (int, float)) else req.expected
    if expiry_failure:
        reason = (f'Required: valid through the submission deadline {deadline}. Verified: {observed} {best.unit}, '
                  f'but the record expires {best.valid_until}, before the deadline.')
        status = 'FAIL'
    else:
        status = 'PASS' if threshold_met else 'FAIL'
        reason = f'Required: {target} {req.unit}. Verified: {observed} {best.unit}.'
    return finish(req, best, status, reason, deadline, as_of)


def finish(req: Requirement, evidence: Evidence, status: str, reason: str, deadline: str | None, as_of: date) -> Check:
    if status == 'PASS':
        return Check(requirement=req, status=status, evidence=evidence, reason=reason,
                     proof=proof_chain(req, evidence, status, reason))
    if req.field == 'insurance':
        action = 'Search for a current insurance certificate. If coverage or validity is insufficient, obtain increased coverage before submission.'
        remediation = 'ACQUIRE CAPABILITY'
    elif req.field == 'certifications':
        action = f'Obtain {req.expected} certification or verify whether the tender permits an eligible partner.'
        remediation = 'PARTNER OR SUBCONTRACT'
    elif req.field in ['languages', 'team']:
        action = 'Confirm internal availability, or bid with a partner that satisfies the requirement.'
        remediation = 'PARTNER OR SUBCONTRACT'
    else:
        action = f'Resolve the {req.field} gap before submission; no verified evidence currently satisfies this rule.'
        remediation = 'ACQUIRE CAPABILITY'
    feasible = None
    if deadline:
        remaining = (date.fromisoformat(deadline) - as_of).days
        feasible = remaining >= LEAD_TIME_DAYS.get(req.field, FIND_EVIDENCE_DAYS)
    return Check(requirement=req, status=status, evidence=evidence, reason=reason, action=action,
                 remediation=remediation, deadline_feasible=feasible,
                 proof=proof_chain(req, evidence, status, reason))


def decide(op: Opportunity, as_of: date) -> Opportunity:
    mandatory = [c for c in op.checks if c.requirement.mandatory]
    op.total = len(mandatory)
    op.verified = sum(c.status == 'PASS' for c in mandatory)
    op.blockers = sum(c.status != 'PASS' for c in mandatory)
    op.blocking_set = [f'{c.requirement.id} · {c.requirement.label}' for c in mandatory if c.status != 'PASS']
    op.needs_review = [f'{c.requirement.id} · {c.requirement.label}' for c in op.checks
                       if c.requirement.compile_status in ['AMBIGUOUS', 'NEEDS_REVIEW', 'UNSUPPORTED']]
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
        if ': ' in line and not line.startswith('§') and not re.match(r'^R\d+ \|', line):
            key, value = line.split(': ', 1)
            facts[key] = (value, source_for(path, line, n))
    requirements = []
    for n, line in enumerate(lines, 1):
        if not re.match(r'^R\d+ \|', line):
            continue
        ident, clause = [p.strip() for p in line.split('|', 1)]
        requirements.append(compile_clause(clause, source_for(path, line, n), ident))
    profile = company_profile()
    as_of = date.fromisoformat(profile['as_of'])
    text = ' '.join(lines)
    matches = [c for c in profile['capabilities'] if c.casefold() in text.casefold()]
    evidence = evidence_catalog(investigate)
    deadline = facts['Deadline'][0]
    checks = [evaluate(r.to_requirement(), evidence, as_of, deadline) for r in requirements]
    executable = [r for r in requirements if r.mandatory and r.status == 'VERIFIED']
    generated: list[dict] = []
    for rule in executable:
        requirement = rule.to_requirement()
        generated += run_cases(generate_for(requirement, deadline), requirement, evaluate, as_of, deadline)
    op = Opportunity(id=path.stem, title=facts['Title'][0], buyer=facts['Buyer'][0],
                     location=facts['Location'][0], deadline=deadline,
                     summary=facts['Scope'][0], source=facts['Title'][1], mode='demo',
                     facts={k.lower(): v[1] for k, v in facts.items()},
                     contract_value=float(facts['Value'][0].split()[0]) if 'Value' in facts else None,
                     value_currency='CHF' if 'Value' in facts else None,
                     value_basis=facts.get('Value basis', ('Not disclosed',))[0],
                     value_source=facts.get('Value', (None, None))[1],
                     document_count=int(facts['Mandatory document count'][0]) if 'Mandatory document count' in facts else None,
                     complete_documents=facts.get('Complete', ('no',))[0] == 'yes',
                     tender_version=1, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                     compiled_total=len(requirements), compiled_executable=len(executable),
                     compiled_review=len(requirements) - len(executable),
                     tests_generated=len(generated), tests_passed=sum(t['passed'] for t in generated),
                     checks=checks,
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
