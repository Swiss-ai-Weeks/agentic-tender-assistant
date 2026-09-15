"""Reproducible regression report: decisions, compilation correctness, citations.

No production or human-label claims. The compilation metrics exist because an
incorrectly compiled rule makes the deterministic engine confidently wrong.
"""
from datetime import UTC, date, datetime
import json

from src.opportunity.compiler import compile_clause
from src.opportunity.engine import ROOT, DEMO, evaluate, extract_demo
from src.opportunity.models import Evidence, Requirement, Source


def run_case(case):
    source = Source(id='controlled-evaluation', document='eligibility-cases.json', quote=case.get('quote', 'Controlled benchmark input'), url='/api/evaluation')
    req = Requirement(id=case['id'], label=case['id'], field=case['field'], operator=case['operator'], expected=case['expected'], unit=case['unit'], source=source.model_copy(update={'quote': 'Controlled requirement input'}))
    records = [] if case['value'] is None else [Evidence(field=case['field'], value=case['value'], unit=case.get('evidence_unit', case['unit']), valid_until=case.get('expiry', '2027-01-01'), source=source)]
    return evaluate(req, records, date(2026, 9, 15)).status


def compile_case(case):
    source = Source(id='controlled-compilation', document='compilation-cases.json', quote=case['clause'], url='/api/evaluation')
    rule = compile_clause(case['clause'], source, case['id'])
    expected = case['expected']
    if rule.status != expected['status']:
        return False, f"status {rule.status} != {expected['status']}"
    if expected['status'] == 'VERIFIED':
        for key in ['field', 'operator']:
            if getattr(rule, key) != expected[key]:
                return False, f'{key} {getattr(rule, key)} != {expected[key]}'
        if rule.expected != expected['expected']:
            return False, f"expected {rule.expected} != {expected['expected']}"
        if 'window_years' in expected and rule.window_years != expected['window_years']:
            return False, f"window {rule.window_years} != {expected['window_years']}"
    return True, ''


def measure():
    dataset = json.loads((ROOT / 'data/evaluation/eligibility-cases.json').read_text())
    results = [{'id': c['id'], 'expected': c['answer'], 'actual': run_case(c)} for c in dataset['cases']]
    correct = sum(r['actual'] == r['expected'] for r in results)
    compilation_cases = json.loads((ROOT / 'data/evaluation/compilation-cases.json').read_text())
    compilation = []
    for case in compilation_cases['clauses']:
        ok, detail = compile_case(case)
        compilation.append({'id': case['id'], 'expected': case['expected']['status'], 'correct': ok, 'detail': detail})
    compilation_errors = sum(not c['correct'] for c in compilation)
    ops = [extract_demo(p) for p in (DEMO / 'tenders').glob('*.txt')]
    citations = [c.requirement.source for op in ops for c in op.checks]
    citations += [c.evidence.source for op in ops for c in op.checks if c.evidence]
    def intact_source(s):
        path = DEMO / s.id.removeprefix('demo/')
        return path.exists() and s.quote in path.read_text() and (not s.line or path.read_text().splitlines()[s.line - 1] == s.quote)
    intact = sum(intact_source(s) for s in citations)
    # Compare the unchanged parsed requirements/decisions with malicious source present.
    security = next(o for o in ops if o.id == 'security')
    injection_unchanged = security.recommendation == 'NO-GO' and security.checks[0].status == 'FAIL'
    return {'status': 'complete', 'generated_at': datetime.now(UTC).isoformat(),
            'label_provenance': dataset['label_provenance'],
            'cases': len(results), 'correct': correct,
            'critical_false_passes': sum(r['actual'] == 'PASS' and r['expected'] != 'PASS' for r in results),
            'compilation_cases': len(compilation), 'compilation_correct': len(compilation) - compilation_errors,
            'compilation_error_rate': round(compilation_errors / len(compilation), 4),
            'compilation_results': compilation,
            'citations_checked': len(citations), 'citations_verified': int(intact),
            'requirements_compiled': sum(o.compiled_total for o in ops),
            'requirements_executable': sum(o.compiled_executable for o in ops),
            'requirements_needs_review': sum(o.compiled_review for o in ops),
            'requirements_expected': sum(o.total for o in ops),
            'requirements_found': sum(o.total for o in ops),
            'tender_tests_generated': sum(o.tests_generated for o in ops),
            'tender_tests_passing': sum(o.tests_passed for o in ops),
            'injection_unchanged': injection_unchanged, 'results': results,
            'unmeasured': ['independent human labels', 'real-document precision/recall', 'semantic citation accuracy',
                           'unsupported factual claims', 'manual qualification time', 'human review time']}


def compilation_failure(report):
    return report['compilation_correct'] != report['compilation_cases'] or report['citations_verified'] != report['citations_checked']


if __name__ == '__main__':
    report = measure()
    target = ROOT / 'docs/evidence/evaluation.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ['results', 'compilation_results']}, indent=2))
    if report['correct'] != report['cases'] or report['critical_false_passes'] or compilation_failure(report):
        raise SystemExit(1)
