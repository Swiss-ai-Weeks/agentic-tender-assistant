"""Loopback-only jury API. Does not edit or restart Hermes infrastructure."""
from datetime import UTC, date, datetime
from pathlib import Path
import hashlib
import json
import threading
import time
from typing import Literal
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.opportunity.compiler import VERSION as COMPILER_VERSION
from src.opportunity.competitors import competitor_landscape
from src.opportunity.engine import ENGINE_VERSION, DEMO, ROOT, company_profile, evaluate, evidence_catalog, extract_demo, rank
from src.opportunity.models import Event, Run
from src.opportunity.simap import CAPTURED, leads, mcp_call, notice_opportunity, relevant
from src.opportunity.sources import store_version
from src.opportunity.strategy import capability_gaps, plan_portfolio, simulate
from src.opportunity.tender_tests import generate_for, run_cases

app = FastAPI(title='Tender Opportunity Agent', docs_url='/api/docs')
runs: dict[str, Run] = {}
lock = threading.RLock()
RUNTIME = ROOT / '.runtime'


class DiscoverRequest(BaseModel):
    mode: Literal['demo', 'live', 'captured'] = 'captured'


class SimulateRequest(BaseModel):
    overlay: list[dict]


class PortfolioRequest(BaseModel):
    capacity_days: float


def scenario_date(mode: str) -> date:
    if mode == 'demo':
        return date.fromisoformat(company_profile()['as_of'])
    return date.today()


def event(run, stage, message):
    with lock:
        run.events.append(Event(at=datetime.now(UTC).isoformat(), stage=stage, message=message))


def get_run(run_id):
    if run_id not in runs:
        raise HTTPException(404, 'This run is unavailable. Start a new discovery.')
    return runs[run_id]


def persist(run):
    RUNTIME.mkdir(exist_ok=True)
    (RUNTIME / (run.id + '.json')).write_text(run.model_dump_json(indent=2))


def discover(run):
    started = time.perf_counter()
    try:
        if run.mode == 'demo':
            files = sorted((DEMO / 'tenders').glob('*.txt'))
            run.discovered = len(files)
            event(run, 'discovery', f'Read {len(files)} synthetic tender specifications. Scenario date: {company_profile()["as_of"]}.')
            for path in files:
                op = extract_demo(path)
                if not op.fit_matches:
                    continue
                run.relevant += 1
                event(run, 'triage', f'{op.title}: {len(op.fit_matches)} profile capability matches.')
                run.opportunities.append(op)
                run.investigated += 1
                event(run, 'qualification', f'{op.title}: {op.verified}/{op.total} mandatory requirements verified; {op.recommendation}.')
        else:
            all_leads = {}
            if run.mode == 'live':
                for term in company_profile()['search_terms']:
                    event(run, 'discovery', f'SIMAP MCP search_tenders: {term}, tender notices published in the last seven days.')
                    from datetime import date, timedelta
                    payload = mcp_call('search_tenders', {'search': term, 'pubTypes': ['tender'], 'lang': 'en',
                                                        'publicationFrom': (date.today()-timedelta(days=7)).isoformat()})
                    RUNTIME.mkdir(exist_ok=True)
                    (RUNTIME / f'{run.id}-search-{term}.json').write_text(json.dumps(payload, indent=2))
                    for lead in leads(payload):
                        all_leads[lead['id']] = lead
                event(run, 'discovery', 'Search is bounded to one page per query; counts are retrieved notices, not all SIMAP opportunities.')
            else:
                payload = json.loads((CAPTURED / 'search-software.json').read_text())
                for lead in leads(payload):
                    all_leads[lead['id']] = lead
                event(run, 'discovery', 'Loaded real SIMAP notices captured 15 September 2026. This is an offline replay, not live availability.')
            run.discovered = len(all_leads)
            candidates = [lead for lead in all_leads.values() if relevant(lead)]
            candidates.sort(key=lambda lead: (-len(relevant(lead)), lead['title']))
            run.relevant = len(candidates)
            event(run, 'triage', f'{len(candidates)} notices match company search terms or capabilities. Inspecting up to 5.')
            for lead in candidates[:5] if run.mode == 'live' else candidates:
                if run.mode == 'live':
                    event(run, 'documents', 'SIMAP MCP get_tender_details: ' + lead['title'])
                    payload = mcp_call('get_tender_details', {'projectId': lead['id'], 'publicationId': lead['publication'], 'lang': 'en', 'fullRaw': True})
                    filename = f'{run.id}-{lead["id"]}.json'
                    (RUNTIME / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
                    source_id = 'runtime/' + filename
                else:
                    path = CAPTURED / (lead['id'] + '.json')
                    if not path.exists():
                        continue
                    payload = json.loads(path.read_text())
                    source_id = 'captured/' + path.name
                op = notice_opportunity(lead, payload, source_id, run.mode)
                meta = store_version(lead['id'], json.dumps(payload, ensure_ascii=False).encode(), lead.get('url') or '')
                op.tender_version, op.sha256, op.retrieved_at = meta['version'], meta['sha256'], meta['retrieved_at']
                run.investigated += 1
                if op.deadline and op.deadline <= datetime.now(UTC).date().isoformat():
                    event(run, 'qualification', f'{op.title}: deadline not confirmed future; excluded from open shortlist.')
                    continue
                run.opportunities.append(op)
                event(run, 'qualification', f'{op.title}: {op.total} published criteria extracted; {op.recommendation}. Full documents still require review.')
        run.opportunities = rank(run.opportunities)
        event(run, 'ranking', f'Ranked {len(run.opportunities)} opportunities. Mandatory eligibility precedes commercial fit.')
        run.status = 'complete'
    except Exception as exc:
        run.status = 'error'
        run.error = str(exc)[:300]
        event(run, 'error', run.error)
    finally:
        run.elapsed_seconds = round(time.perf_counter() - started, 3)
        persist(run)


@app.get('/api/company')
def company():
    return {**company_profile(), 'evidence': [e.model_dump() for e in evidence_catalog()],
            'knowledge_documents': company_profile()['knowledge_evidence']}


@app.post('/api/runs', status_code=202)
def start(body: DiscoverRequest, tasks: BackgroundTasks):
    with lock:
        if any(r.status == 'running' for r in runs.values()):
            raise HTTPException(409, 'Discovery is already running. Wait for the current run.')
        if len(runs) >= 40:
            runs.pop(next(iter(runs)))
        profile_hash = hashlib.sha256((DEMO / 'company.json').read_bytes()).hexdigest()[:8]
        run = Run(id=uuid4().hex, mode=body.mode, profile_version=profile_hash,
                  rule_compiler_version=COMPILER_VERSION, engine_version=ENGINE_VERSION)
        runs[run.id] = run
        tasks.add_task(discover, run)
        return run


@app.get('/api/runs/{run_id}')
def status(run_id: str):
    with lock:
        return get_run(run_id).model_copy(deep=True)


@app.post('/api/runs/{run_id}/evidence')
def search_evidence(run_id: str):
    with lock:
        run = get_run(run_id)
        if run.status != 'complete':
            raise HTTPException(409, 'Wait until discovery completes.')
        if run.mode != 'demo':
            raise HTTPException(409, 'Real bidder evidence is not configured. Review the notice and provide verified evidence; synthetic certificates cannot qualify a real bidder.')
        before = {op.id: (op.recommendation, op.verified) for op in run.opportunities}
        event(run, 'evidence', 'Searching the configured company evidence folder for unresolved requirements.')
        files = company_profile()['knowledge_evidence']
        for filename in files:
            event(run, 'evidence', 'Read ' + filename + '; extracting supported fields and checking validity.')
        run.opportunities = rank([extract_demo(DEMO / 'tenders' / (op.id + '.txt'), True) for op in run.opportunities])
        run.searched_evidence = True
        for op in run.opportunities:
            if before[op.id] != (op.recommendation, op.verified):
                event(run, 'updated', f'{op.title}: {before[op.id][1]}/{op.total} → {op.verified}/{op.total}; {before[op.id][0]} → {op.recommendation}.')
        event(run, 'evidence', 'Evidence search completed. Requirements without supporting evidence remain unresolved.')
        persist(run)
        return run


@app.get('/api/runs/{run_id}/landscape')
def landscape(run_id: str, tender: str | None = None):
    run = get_run(run_id)
    if run.status != 'complete':
        raise HTTPException(409, 'Wait until discovery completes.')
    op = next((o for o in run.opportunities if o.id == tender), run.opportunities[0] if run.opportunities else None)
    if op is None:
        raise HTTPException(404, 'No qualified tender in this run.')
    executable = [c.requirement for c in op.checks if c.requirement.compile_status == 'VERIFIED']
    result = competitor_landscape(executable, op.summary, op.deadline)
    result['tender'] = {'id': op.id, 'title': op.title, 'buyer': op.buyer, 'deadline': op.deadline}
    return result


@app.get('/api/runs/{run_id}/gaps')
def gaps(run_id: str):
    run = get_run(run_id)
    if run.status != 'complete':
        raise HTTPException(409, 'Wait until discovery completes.')
    result = capability_gaps(run.opportunities)
    pipeline = sum(o.contract_value or 0 for o in run.opportunities if o.recommendation in ['GO', 'CONDITIONAL GO'])
    return {'gaps': result, 'eligible_pipeline_chf': pipeline,
            'potential_value_affected_chf': sum(g['published_value_chf'] for g in result)}


@app.post('/api/runs/{run_id}/simulate')
def run_simulation(run_id: str, body: SimulateRequest):
    run = get_run(run_id)
    if run.status != 'complete':
        raise HTTPException(409, 'Wait until discovery completes.')
    if not body.overlay:
        raise HTTPException(422, 'Provide at least one overlay fact.')
    return simulate(run.opportunities, body.overlay, scenario_date(run.mode), evidence_catalog(run.mode == 'demo'))


@app.post('/api/runs/{run_id}/portfolio')
def portfolio(run_id: str, body: PortfolioRequest):
    run = get_run(run_id)
    if run.status != 'complete':
        raise HTTPException(409, 'Wait until discovery completes.')
    if body.capacity_days <= 0:
        raise HTTPException(422, 'Capacity must be a positive number of days.')
    return plan_portfolio(run.opportunities, body.capacity_days)


@app.get('/api/runs/{run_id}/tests')
def generated_tests(run_id: str):
    run = get_run(run_id)
    if run.status != 'complete':
        raise HTTPException(409, 'Wait until discovery completes.')
    if run.mode != 'demo':
        return {'tests': [], 'note': 'Generated tender tests apply to compiled executable rules; real notices require the full specification first.'}
    as_of = scenario_date(run.mode)
    tests = []
    for op in run.opportunities:
        for check in op.checks:
            if check.requirement.mandatory and check.requirement.compile_status == 'VERIFIED':
                cases = generate_for(check.requirement, op.deadline)
                tests += run_cases(cases, check.requirement, evaluate, as_of, op.deadline)
    return {'tests': tests, 'generated': len(tests), 'passing': sum(t['passed'] for t in tests)}


@app.get('/api/evaluation')
def evaluation():
    path = ROOT / 'docs/evidence/evaluation.json'
    return json.loads(path.read_text()) if path.exists() else {'status': 'not_run'}


@app.get('/api/system')
def system():
    return {'api': 'Connected · isolated FastAPI service', 'agent': 'Deterministic workflow controller; Hermes integration not yet wired to this UI',
            'model': 'No model used by this qualification service; Nemotron is the planned semantic compiler behind the deterministic validation gate',
            'compute': 'Local CPU; remote H100 workload unchanged',
            'compiler': COMPILER_VERSION + ' · clause → executable rule, ambiguous clauses stay AMBIGUOUS',
            'engine': ENGINE_VERSION + ' · deterministic PASS/FAIL/UNKNOWN, deadline-aware validity',
            'hermes': 'Last read-only audit: API healthy; dashboard empty response. Not continuously monitored.',
            'simap': 'Read-only stdio MCP; live connectivity is checked by each discovery run',
            'privacy': 'Live search sends configured company search terms to SIMAP. Demo evidence is processed locally.',
            'limitations': 'Real notice extraction is partial. Full external specifications, independent human labels and measured manual-review baselines are pending.'}


@app.get('/api/sources/{source_id:path}')
def source(source_id: str):
    if source_id.startswith('captured/'):
        root, relative = CAPTURED, source_id.removeprefix('captured/')
    elif source_id.startswith('runtime/'):
        root, relative = RUNTIME, source_id.removeprefix('runtime/')
    else:
        root, relative = DEMO, source_id
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or path.suffix not in ['.txt', '.json', '.pdf']:
        raise HTTPException(404, 'Source not available')
    media = 'application/pdf' if path.suffix == '.pdf' else 'text/plain; charset=utf-8'
    return FileResponse(path, media_type=media, headers={'X-Content-Type-Options': 'nosniff'})


@app.get('/api/runs/{run_id}/export')
def export(run_id: str):
    run = get_run(run_id)
    persist(run)
    return FileResponse(RUNTIME / (run.id + '.json'), media_type='application/json', filename='tender-opportunity-review.json')
