from datetime import date
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from src.opportunity.api import app, runs
from src.opportunity.engine import DEMO, ROOT, decide, evaluate, extract_demo, rank
from src.opportunity.evaluation import run_case
from src.opportunity.simap import CAPTURED, leads, notice_opportunity

CASES=json.loads((ROOT/'data/evaluation/eligibility-cases.json').read_text())['cases']

@pytest.mark.parametrize('case',CASES,ids=[c['id'] for c in CASES])
def test_decisions(case):
    assert run_case(case)==case['answer']


def test_real_evidence_update_and_hard_fail_ranking():
    before=extract_demo(DEMO/'tenders/data-platform.txt')
    after=extract_demo(DEMO/'tenders/data-platform.txt',True)
    no=extract_demo(DEMO/'tenders/security.txt')
    assert (before.recommendation,before.verified)==('CONDITIONAL GO',4)
    assert (after.recommendation,after.verified)==('GO',5)
    assert after.checks[-1].evidence.source.document=='insurance_renewal_2026.txt'
    assert no.contract_value>after.contract_value
    assert rank([no,after])[0].id==after.id
    assert after.effort_days[0]<before.effort_days[0]
    assert no.recommendation=='NO-GO'


def test_no_vacuous_pass_and_expiry():
    op=extract_demo(DEMO/'tenders/infrastructure.txt')
    op.checks=[]
    assert decide(op,date(2026,9,15)).recommendation!='GO'
    op=extract_demo(DEMO/'tenders/infrastructure.txt')
    assert decide(op,date(2026,10,10)).recommendation=='NO-GO'


def test_family_fail_dominates_unknown_and_pass():
    op=extract_demo(DEMO/'tenders/data-platform.txt')
    assert op.families['Financial / Insurance']=='UNKNOWN'
    op.checks[-1].status='FAIL'
    assert decide(op,date(2026,9,15)).families['Financial / Insurance']=='FAIL'


def test_conflicting_evidence_stays_unknown():
    op=extract_demo(DEMO/'tenders/data-platform.txt',True)
    c=op.checks[-1]
    other=c.evidence.model_copy(update={'value':5000000})
    assert evaluate(c.requirement,[c.evidence,other],date(2026,9,15)).status=='UNKNOWN'


def test_captured_notice_never_invents_value_or_go():
    lead=next(l for l in leads(json.loads((CAPTURED/'search-software.json').read_text())) if l['id']=='b1bd13b4-ec34-4786-814e-1680a39e03c2')
    op=notice_opportunity(lead,json.loads((CAPTURED/(lead['id']+'.json')).read_text()),'captured/'+lead['id']+'.json','captured')
    assert op.contract_value is None
    assert op.value_source is None
    assert len(op.checks)==8
    assert op.recommendation!='GO'
    assert op.effort=='NOT ESTIMATED'
    assert all(c.status=='UNKNOWN' and c.requirement.source.section.startswith('/lots/') for c in op.checks)


def test_api_run_inspection_evidence_export_and_sources():
    runs.clear()
    with TestClient(app) as client:
        response=client.post('/api/runs',json={'mode':'demo'})
        assert response.status_code==202
        ident=response.json()['id']
        data=client.get('/api/runs/'+ident).json()
        assert data['status']=='complete'
        assert data['discovered']==3
        assert [o['recommendation'] for o in data['opportunities']]==['GO','CONDITIONAL GO','NO-GO']
        updated=client.post('/api/runs/'+ident+'/evidence',json={}).json()
        assert sum(o['recommendation']=='GO' for o in updated['opportunities'])==2
        assert updated['searched_evidence']
        assert client.get('/api/runs/'+ident+'/export').status_code==200
        assert client.get('/api/sources/evidence/insurance_renewal_2026.txt').status_code==200
        assert client.get('/api/sources/%2E%2E/%2E%2E/pyproject.toml').status_code==404
        assert client.post('/api/runs',json={'mode':'invented'}).status_code==422


def test_real_mode_cannot_use_demo_certificates():
    runs.clear()
    with TestClient(app) as client:
        ident=client.post('/api/runs',json={'mode':'captured'}).json()['id']
        data=client.get('/api/runs/'+ident).json()
        assert data['status']=='complete'
        assert len(data['opportunities'])>=1
        assert all(o['recommendation']!='GO' for o in data['opportunities'])
        assert client.post('/api/runs/'+ident+'/evidence',json={}).status_code==409


def test_network_failure_stays_live_error(monkeypatch):
    from src.opportunity import api
    runs.clear()
    def fail(*args,**kwargs):raise RuntimeError('Offline test')
    monkeypatch.setattr(api,'mcp_call',fail)
    with TestClient(app) as client:
        ident=client.post('/api/runs',json={'mode':'live'}).json()['id']
        data=client.get('/api/runs/'+ident).json()
        assert data['status']=='error'
        assert data['mode']=='live'
        assert data['opportunities']==[]
        assert data['error']=='Offline test'
