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
    assert after.checks[4].evidence.source.document=='insurance_renewal_2026.txt'
    assert no.contract_value>after.contract_value
    assert rank([no,after])[0].id==after.id
    assert after.effort_days[0]<before.effort_days[0]
    assert no.recommendation=='NO-GO'


def test_ambiguous_clause_stays_out_of_the_gate():
    op=extract_demo(DEMO/'tenders/data-platform.txt')
    review=op.checks[5]
    assert review.requirement.compile_status=='AMBIGUOUS'
    assert not review.requirement.mandatory
    assert review.status=='UNKNOWN'
    assert any(x.startswith('R6') for x in op.needs_review)
    assert (op.compiled_total,op.compiled_executable,op.compiled_review)==(6,5,1)


def test_expiry_before_deadline_is_proved_not_met():
    op=extract_demo(DEMO/'tenders/servicedesk.txt')
    assert op.deadline=='2028-01-15'
    refs=op.checks[1]
    assert refs.status=='FAIL'
    assert 'expires 2026-12-31, before the deadline' in refs.reason
    assert op.recommendation=='NO-GO'
    assert len(op.blocking_set)==3


def test_generated_tender_tests_hold():
    for name in ['infrastructure','data-platform','security','servicedesk']:
        op=extract_demo(DEMO/'tenders'/(name+'.txt'))
        assert op.tests_generated>0 and op.tests_generated==op.tests_passed


def test_proof_chain_present():
    op=extract_demo(DEMO/'tenders/infrastructure.txt')
    proof=op.checks[0].proof
    assert [s.stage for s in proof]==['CLAUSE','RULE','FACT','EVIDENCE','VERDICT']
    assert proof[0].text.startswith('The bidder must hold')
    assert 'ISO 27001' in proof[1].text


def test_no_vacuous_pass_and_expiry():
    op=extract_demo(DEMO/'tenders/infrastructure.txt')
    op.checks=[]
    assert decide(op,date(2026,9,15)).recommendation!='GO'
    op=extract_demo(DEMO/'tenders/infrastructure.txt')
    assert decide(op,date(2026,10,10)).recommendation=='NO-GO'


def test_family_fail_dominates_unknown_and_pass():
    op=extract_demo(DEMO/'tenders/data-platform.txt')
    assert op.families['Financial / Insurance']=='UNKNOWN'
    op.checks[4].status='FAIL'
    assert decide(op,date(2026,9,15)).families['Financial / Insurance']=='FAIL'


def test_conflicting_evidence_stays_unknown():
    op=extract_demo(DEMO/'tenders/data-platform.txt',True)
    c=op.checks[4]
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
        assert data['discovered']==4
        assert [o['recommendation'] for o in data['opportunities']]==['GO','CONDITIONAL GO','NO-GO','NO-GO']
        assert data['rule_compiler_version'].startswith('compiler/')
        assert data['engine_version'].startswith('engine/')
        tests=client.get('/api/runs/'+ident+'/tests').json()
        assert tests['generated']==tests['passing'] and tests['generated']>50
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


def test_landscape_gaps_simulation_portfolio_endpoints():
    runs.clear()
    with TestClient(app) as client:
        ident=client.post('/api/runs',json={'mode':'demo'}).json()['id']
        client.get('/api/runs/'+ident)
        landscape=client.get('/api/runs/'+ident+'/landscape').json()
        assert landscape['tender']['id']=='infrastructure'
        orgs={row['org_id']:row for row in landscape['orgs']}
        assert orgs['helvetia-it']['cells']['R1']['status']=='PUBLICLY SUPPORTED'
        assert orgs['alpen-technik']['cells']['R1']['status']=='PUBLIC NON-MATCH'
        assert orgs['jura-consulting']['cells']['R1']['status']=='UNKNOWN'
        gaps=client.get('/api/runs/'+ident+'/gaps').json()
        assert gaps['gaps'] and gaps['gaps'][0]['published_value_chf']>0
        before={o['id']:o['recommendation'] for o in client.get('/api/runs/'+ident).json()['opportunities']}
        simulation=client.post('/api/runs/'+ident+'/simulate',json={'overlay':[{'field':'insurance','value':10000000,'unit':'CHF','label':'Liability insurance CHF 10M'}]}).json()
        after={o['id']:o['recommendation'] for o in simulation['opportunities']}
        assert before==after or simulation['affected_tenders']
        assert simulation['pipeline_after_chf']>=simulation['pipeline_before_chf']
        verified={o['id']:o['recommendation'] for o in client.get('/api/runs/'+ident).json()['opportunities']}
        assert verified==before  # simulation must not mutate verified state
        portfolio=client.post('/api/runs/'+ident+'/portfolio',json={'capacity_days':6}).json()
        assert portfolio['used_days']<=6.001
        assert portfolio['selected'] or portfolio['deferred']
        assert client.post('/api/runs/'+ident+'/simulate',json={'overlay':[]}).status_code==422
