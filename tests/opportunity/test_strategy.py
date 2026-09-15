"""Strategy layer: capability gaps, non-mutating simulation, portfolio capacity."""
from datetime import date

from src.opportunity.engine import DEMO, extract_demo
from src.opportunity.strategy import capability_gaps, plan_portfolio, simulate


def _ops():
    return [extract_demo(p) for p in sorted((DEMO/'tenders').glob('*.txt'))]


def _as_of():
    return date(2026, 9, 15)


def test_capability_gaps_aggregate_blockers_with_value():
    gaps = capability_gaps(_ops())
    insurance = next(g for g in gaps if g['field']=='insurance')
    assert insurance['tender_count']>=2
    assert insurance['published_value_chf']>0
    assert any(g['field']=='certifications' for g in gaps)
    top = gaps[0]
    assert top['published_value_chf']>=gaps[-1]['published_value_chf']


def test_simulation_overlays_without_mutating_verified_state():
    ops = _ops()
    before = [(o.id, o.recommendation, o.verified, o.total) for o in ops]
    overlay = [{'field':'insurance','value':10000000,'unit':'CHF','label':'Liability insurance CHF 10M'},
               {'field':'certifications','value':['ISO 27001','ISO 9001','ISO 20000'],'unit':'names','label':'Add ISO 20000'}]
    result = simulate(ops, overlay, _as_of(), evidence=[])
    assert result['basis'].startswith('SIMULATION ONLY')
    assert result['pipeline_after_chf']>=result['pipeline_before_chf']
    assert result['affected_tenders'], 'overlay should change at least one tender'
    assert [(o.id, o.recommendation, o.verified, o.total) for o in ops]==before
    simulated_checks = [c for o in result['opportunities'] for c in o.checks if c.simulated]
    assert simulated_checks
    assert all(c.evidence.trust=='SIMULATED' for c in simulated_checks)


def test_portfolio_respects_capacity_and_explains():
    ops = _ops()
    plan = plan_portfolio(ops, 6)
    assert plan['used_days']<=6.001
    assert plan['total_value_chf']>0
    assert all(item['days'] for item in plan['selected'])
    plan_zero = plan_portfolio(ops, 0.5)
    assert plan_zero['selected']==[] and plan_zero['deferred']
