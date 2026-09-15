"""Loopback-only jury API. Does not edit or restart Hermes infrastructure."""
import hashlib
import json
import threading
import time
from datetime import UTC, date, datetime
from typing import Literal
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.opportunity.competitors import competitor_landscape
from src.opportunity.compiler import VERSION as COMPILER_VERSION
from src.opportunity.engine import (
    DEMO,
    ENGINE_VERSION,
    ROOT,
    company_profile,
    decide,
    evaluate,
    evidence_catalog,
    extract_demo,
    rank,
)
from src.opportunity.models import Event, Opportunity, Run, Source
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
    return datetime.now(UTC).date()


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
    try:
        from src.opportunity.db import record_qualification_run
        record_qualification_run(run, run.opportunities)
    except Exception:
        pass


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
                                                        'publicationFrom': (datetime.now(UTC).date()-timedelta(days=7)).isoformat()})
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
    # Background discovery must report every transport/extraction failure to the
    # run instead of crashing the worker; FastAPI turns it into a typed run error.
    except Exception as exc:  # noqa: BLE001
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
    result = competitor_landscape(executable, op.summary, op.deadline, our_checks=op.checks)
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
    executable = sum(o.compiled_executable for o in run.opportunities)
    total = sum(o.compiled_total for o in run.opportunities)
    review = sum(o.compiled_review for o in run.opportunities)
    as_of = scenario_date(run.mode)
    tests = []
    for op in run.opportunities:
        for check in op.checks:
            if check.requirement.mandatory and check.requirement.compile_status == 'VERIFIED':
                cases = generate_for(check.requirement, op.deadline)
                tests += run_cases(cases, check.requirement, evaluate, as_of, op.deadline)
    result = {'tests': tests, 'generated': len(tests), 'passing': sum(t['passed'] for t in tests),
              'compiled_total': total, 'compiled_executable': executable, 'compiled_review': review}
    if executable:
        result['note'] = 'Boundary tests are generated only from mandatory rules that compiled VERIFIED.'
    else:
        result['note'] = 'No notice-level criterion compiled into an executable rule; full specifications require human review before tests can be generated.'
    return result


@app.get('/api/corrigendum/demo')
def corrigendum_demo():
    """Controlled corrigendum walkthrough: v1 → v2 recompilation with the
    qualification delta computed by the deterministic engine."""
    from src.opportunity.compiler import compile_clause
    from src.opportunity.corrigendum import demo_pair, recompile_diff
    old_clauses, new_clauses = demo_pair()
    source = Source(id='corrigendum-demo', document='corrigendum v1→v2', quote='Controlled corrigendum pair (synthetic).', url='/api/corrigendum/demo')
    diff = recompile_diff(old_clauses, new_clauses, source)
    as_of = scenario_date('demo')
    evidence = evidence_catalog(True)

    def qualify(clauses: dict[str, str]):
        rules = [compile_clause(text, source, ident) for ident, text in clauses.items()]
        checks = [evaluate(r.to_requirement(), evidence, as_of, '2026-10-02') for r in rules]
        op = Opportunity(id='corrigendum', title='Corrigendum walkthrough', buyer='Synthetic', location='',
                         deadline='2026-10-02', summary='', source=source, mode='demo',
                         complete_documents=True, checks=checks)
        return decide(op, as_of)

    before, after = qualify(old_clauses), qualify(new_clauses)
    return {**diff,
            'qualification': {'before': {'verified': f'{before.verified}/{before.total}', 'recommendation': before.recommendation},
                              'after': {'verified': f'{after.verified}/{after.total}', 'recommendation': after.recommendation}}}


@app.get('/api/evaluation')
def evaluation():
    path = ROOT / 'docs/evidence/evaluation.json'
    return json.loads(path.read_text()) if path.exists() else {'status': 'not_run'}


@app.get('/api/db/stats')
def db_stats():
    from src.opportunity.db import get_db_stats
    return get_db_stats()


@app.get('/api/competitors/candidates')
def competitor_candidates(scope: str = "IT infrastructure operations", buyer: str = "Demonstration Canton of Vaud"):
    from src.opportunity.competitors import generate_competitor_candidates
    return {"candidates": generate_competitor_candidates(scope, buyer)}


@app.get('/api/system')
def system():
    from src.opportunity.db import get_db_stats
    from src.opportunity.nemotron import default_compiler
    stats = get_db_stats()
    llm = default_compiler.status()
    if llm['state'] == 'disabled':
        model_text = ('Optional model candidate generation is DISABLED (no model contacted; '
                      'deterministic compiler only). Set TENDER_LLM_ENABLED=1 with TENDER_LLM_BASE_URL '
                      'and TENDER_LLM_MODEL to enable explicit candidate proposals.')
    elif llm['state'] == 'configured':
        model_text = (f"Optional model candidate generation is CONFIGURED (model={llm['model']}, "
                      f"endpoint={llm['endpoint']}). Candidates are used only on explicit request "
                      "and only after deterministic clause-anchored validation; the model never decides eligibility.")
    else:
        model_text = ('Optional model candidate generation is INCOMPLETE: ' + llm['detail']
                      + ' Deterministic compiler only; no model contacted.')
    return {
        'model': model_text,
        'model_state': llm['state'],
        'model_endpoint': llm['endpoint'],
        'model_name': llm['model'],
        'compute': 'Local application runtime (no fixed GPU claim; inference endpoint, if enabled, is configured via TENDER_LLM_BASE_URL)',
        'runtime': 'FastAPI loopback service (port 8090 in this environment); Hermes/NAT integration is deployment-specific, not asserted here',
        'data': 'SIMAP public procurement API + immutable local raw sources + public award registries',
        'verification': 'Tender Compiler (clause → executable IR) + deterministic rule engine (PASS/FAIL/UNKNOWN)',
        'workflow': 'DISCOVER → COMPILE → VERIFY → COMPARE → PRIORITIZE → PROVE → ACT',
        'database': f"SQLite authoritative provenance database ({stats['total_records']} relational records across 13 tables; PostgreSQL schema at data/schema.sql)",
        'security': 'Prompt-injection handling: detected instruction-like text is isolated as untrusted data and reported; verdicts come from the deterministic engine, not the model',
        'limitations': 'External live SIMAP notices undergo notice-level extraction; full external annexes require human review before binding bids. '
                       'Evaluation labels are developer-authored regression fixtures; independent human validation is pending.'
    }


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


UI_DIST = ROOT / 'ui' / 'dist'
if UI_DIST.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount('/', StaticFiles(directory=str(UI_DIST), html=True), name='ui')
