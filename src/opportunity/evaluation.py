"""Reproducible regression report. No production or human-label claims."""
from datetime import UTC, date, datetime
import json

from src.opportunity.engine import ROOT, DEMO, evaluate, extract_demo
from src.opportunity.models import Evidence, Requirement, Source


def run_case(case):
    source = Source(id='controlled-evaluation', document='eligibility-cases.json', quote=case.get('quote','Controlled benchmark input'), url='/api/evaluation')
    req = Requirement(id=case['id'], label=case['id'], field=case['field'], operator=case['operator'], expected=case['expected'], unit=case['unit'], source=source.model_copy(update={'quote':'Controlled requirement input'}))
    records = [] if case['value'] is None else [Evidence(field=case['field'],value=case['value'],unit=case.get('evidence_unit',case['unit']),valid_until=case.get('expiry','2027-01-01'),source=source)]
    return evaluate(req, records, date(2026,9,15)).status


def measure():
    dataset = json.loads((ROOT/'data/evaluation/eligibility-cases.json').read_text())
    results = [{'id':c['id'],'expected':c['answer'],'actual':run_case(c)} for c in dataset['cases']]
    correct = sum(r['actual']==r['expected'] for r in results)
    ops = [extract_demo(p) for p in (DEMO/'tenders').glob('*.txt')]
    citations = [c.requirement.source for op in ops for c in op.checks]
    citations += [c.evidence.source for op in ops for c in op.checks if c.evidence]
    intact = sum(s.quote in (DEMO/s.id).read_text() and (not s.line or (DEMO/s.id).read_text().splitlines()[s.line-1]==s.quote) for s in citations)
    # Compare the unchanged parsed requirements/decisions with malicious source present.
    security = next(o for o in ops if o.id=='security')
    injection_unchanged = security.recommendation == 'NO-GO' and security.checks[0].status=='FAIL'
    return {'status':'complete', 'generated_at':datetime.now(UTC).isoformat(), 'label_provenance':dataset['label_provenance'],
            'cases':len(results), 'correct':correct, 'critical_false_passes':sum(r['actual']=='PASS' and r['expected']!='PASS' for r in results),
            'citations_checked':len(citations),'citations_verified':intact,
            'requirements_expected':13,'requirements_found':sum(o.total for o in ops),
            'injection_unchanged':injection_unchanged, 'results':results,
            'unmeasured':['independent human labels','real-document precision/recall','semantic citation accuracy','unsupported factual claims','manual qualification time','human review time']}


if __name__ == '__main__':
    report=measure()
    target=ROOT/'docs/evidence/evaluation.json'
    target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))
    if report['correct'] != report['cases'] or report['critical_false_passes']:
        raise SystemExit(1)
