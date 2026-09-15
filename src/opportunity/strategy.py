"""Strategic intelligence: capability gaps, what-if simulation, portfolio.

Simulations never modify verified company state: overlay facts are tagged
SIMULATED and all results are returned as a separate scenario object.
"""
from src.opportunity.engine import decide, evaluate, rule_text
from src.opportunity.models import Evidence, Opportunity, Source

SIM_SOURCE = Source(id='simulation-overlay', document='what-if overlay', quote='Simulated fact — not verified company evidence.',
                    url='/api/system', trust='SIMULATED')


def capability_gaps(opportunities: list[Opportunity]) -> list[dict]:
    """Aggregate repeated mandatory blockers across tenders, with the published
    tender value they affect. Expressed as potential value affected, never as
    promised revenue."""
    aggregate: dict[tuple, dict] = {}
    for op in opportunities:
        for check in op.checks:
            if not check.requirement.mandatory or check.status == 'PASS':
                continue
            key = (check.requirement.field, json_key(check.requirement))
            gap = aggregate.setdefault(key, {'field': check.requirement.field, 'requirement': check.requirement.label,
                                             'target': target_text(check.requirement), 'tenders': [], 'published_value_chf': 0.0,
                                             'statuses': set()})
            if op.id not in [t['id'] for t in gap['tenders']]:
                gap['tenders'].append({'id': op.id, 'title': op.title, 'deadline': op.deadline,
                                       'value': op.contract_value, 'status': check.status,
                                       'remediation': check.remediation, 'deadline_feasible': check.deadline_feasible})
            gap['published_value_chf'] += op.contract_value or 0
            gap['statuses'].add(check.status)
    gaps = []
    for gap in aggregate.values():
        gap['tender_count'] = len(gap['tenders'])
        gap['statuses'] = sorted(gap['statuses'])
        gap['feasible_before_deadlines'] = sum(1 for t in gap['tenders'] if t['deadline_feasible'])
        gaps.append(gap)
    return sorted(gaps, key=lambda g: (-g['published_value_chf'], -g['tender_count']))


def json_key(req) -> str:
    return rule_text(req)


def target_text(req) -> str:
    if isinstance(req.expected, (int, float)):
        return f'{req.expected:,.0f} {req.unit}'.strip()
    return str(req.expected)


def simulate(opportunities: list[Opportunity], overlay: list[dict], as_of, evidence: list[Evidence]) -> dict:
    """Recompute qualification with hypothetical facts layered on top of the
    verified company evidence. Verified state is left untouched."""
    overlay_facts = []
    for item in overlay:
        overlay_facts.append(Evidence(field=item['field'], value=item['value'], unit=item.get('unit', ''),
                                      valid_until=item.get('valid_until', '2030-12-31'), source=SIM_SOURCE, trust='SIMULATED'))
    before_value = sum(o.contract_value or 0 for o in opportunities if o.recommendation in ['GO', 'CONDITIONAL GO'])
    scenarios, affected = [], []
    for op in opportunities:
        scenario = op.model_copy(deep=True)
        baseline = {c.requirement.id: c.status for c in scenario.checks}
        recomputed = [evaluate(c.requirement, evidence + overlay_facts, as_of, scenario.deadline) for c in scenario.checks]
        for check in recomputed:
            check.simulated = check.evidence is not None and check.evidence.trust == 'SIMULATED'
        scenario.checks = recomputed
        changed = {c.requirement.id: [baseline[c.requirement.id], c.status]
                   for c in recomputed if baseline[c.requirement.id] != c.status}
        decision_before = op.recommendation
        decide(scenario, as_of)
        scenario.risks = list(dict.fromkeys(scenario.risks))
        if changed:
            changed['__label__'] = [decision_before, scenario.recommendation]
            affected.append({'id': scenario.id, 'title': scenario.title, 'before': decision_before,
                             'after': scenario.recommendation, 'changed': changed})
        scenarios.append(scenario)
    after_value = sum(o.contract_value or 0 for o in scenarios if o.recommendation in ['GO', 'CONDITIONAL GO'])
    return {'basis': 'SIMULATION ONLY — hypothetical overlay facts; verified company state unchanged.',
            'overlay': [{'field': o['field'], 'value': o['value'], 'unit': o.get('unit', ''), 'label': o.get('label')} for o in overlay],
            'pipeline_before_chf': before_value, 'pipeline_after_chf': after_value,
            'potential_value_affected_chf': after_value - before_value,
            'affected_tenders': affected, 'opportunities': scenarios}


def plan_portfolio(opportunities: list[Opportunity], capacity_days: float) -> dict:
    """Capacity-constrained, explainable selection. Ranks by published value per
    estimated bid day among eligible candidates; never invents capacity."""
    candidates = [o for o in opportunities if o.recommendation in ['GO', 'CONDITIONAL GO'] and o.effort_days]
    ranked = sorted(candidates, key=lambda o: (-(o.contract_value or 0) / o.effort_days[0], o.effort_days[0]))
    selected, deferred, used = [], [], 0.0
    for op in ranked:
        days = op.effort_days[0]
        if used + days <= capacity_days:
            selected.append(op)
            used += days
        else:
            deferred.append({'id': op.id, 'title': op.title, 'days': days, 'value': op.contract_value,
                             'reason': f'Would need {days} days; {round(capacity_days - used, 1)} of the capacity budget remains.'})
    skipped = [{'id': o.id, 'title': o.title,
                'reason': 'No GO/CONDITIONAL GO decision or effort is not yet estimable.'}
               for o in opportunities if o not in candidates]
    return {'capacity_days': capacity_days, 'used_days': round(used, 1),
            'selected': [{'id': o.id, 'title': o.title, 'days': o.effort_days[0], 'value': o.contract_value,
                          'recommendation': o.recommendation} for o in selected],
            'deferred': deferred, 'excluded': skipped,
            'total_value_chf': sum(o.contract_value or 0 for o in selected),
            'explanation': ['Ranked by published value per estimated bid day; eligibility gates first.',
                            'Effort figures are planning estimates from the company profile, not measured costs.']}
