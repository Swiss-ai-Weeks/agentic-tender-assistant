"""Competitor landscape semantics: entity resolution and the three public states."""
from src.opportunity.competitors import competitor_landscape, resolve_org
from src.opportunity.engine import DEMO, extract_demo


def test_entity_resolution_over_aliases():
    data = __import__('src.opportunity.facts', fromlist=['competitor_data']).competitor_data()
    assert resolve_org('Helvetia IT', data['orgs'])['id']=='helvetia-it'
    assert resolve_org('AlpenTech', data['orgs'])['id']=='alpen-technik'
    assert resolve_org('Unknown GmbH', data['orgs']) is None


def _landscape(tender):
    op = extract_demo(DEMO/'tenders'/(tender+'.txt'))
    return op, competitor_landscape([c.requirement for c in op.checks], op.summary, op.deadline)


def test_three_states_on_iso_requirement():
    op, landscape = _landscape('infrastructure')
    cells = {row['org_id']: row['cells'] for row in landscape['orgs']}
    assert cells['helvetia-it']['R1']['status']=='PUBLICLY SUPPORTED'
    assert cells['alpen-technik']['R1']['status']=='PUBLIC NON-MATCH'
    assert cells['jura-consulting']['R1']['status']=='UNKNOWN'
    assert 'never' in landscape['semantics']['UNKNOWN'].casefold()


def test_reference_counts_use_window_and_stay_unknown_below_threshold():
    op, landscape = _landscape('infrastructure')
    cells = {row['org_id']: row['cells'] for row in landscape['orgs']}
    supported = cells['helvetia-it']['R2']
    assert supported['status']=='PUBLICLY SUPPORTED' and 'comparable public awards' in supported['note']
    below = cells['alpen-technik']['R2']
    assert below['status']=='UNKNOWN'
    assert 'proves nothing' in below['note']
    # With a narrower scope fewer awards count as comparable, and the state
    # honestly degrades to UNKNOWN instead of inventing support.
    narrow = competitor_landscape([c.requirement for c in op.checks], 'IT infrastructure operations', op.deadline)
    narrow_cells = {row['org_id']: row['cells'] for row in narrow['orgs']}
    assert narrow_cells['helvetia-it']['R2']['status']=='UNKNOWN'


def test_unknown_never_claims_inability():
    op, landscape = _landscape('servicedesk')
    for row in landscape['orgs']:
        if row.get('is_us'):
            continue
        insurance = row['cells']['R1']
        assert insurance['status'] in ['UNKNOWN']  # no public insurance registry data exists


def test_hpe_entity_resolution_and_iso_support():
    from src.opportunity.competitors import resolve_organization
    assert resolve_organization('HPE')['id'] == 'hpe'
    assert resolve_organization('Hewlett Packard Enterprise')['id'] == 'hpe'
    assert resolve_organization('Hewlett Packard Enterprise Switzerland GmbH')['id'] == 'hpe'
    assert resolve_organization('CHE-105.856.321')['id'] == 'hpe'

    op, landscape = _landscape('infrastructure')
    cells = {row['org_id']: row['cells'] for row in landscape['orgs']}
    assert 'hpe' in cells
    assert cells['hpe']['R1']['status'] == 'PUBLICLY SUPPORTED'


def test_our_company_in_landscape_and_requirement_advantage():
    op = extract_demo(DEMO / 'tenders' / 'infrastructure.txt')
    landscape = competitor_landscape([c.requirement for c in op.checks], op.summary, op.deadline, our_checks=op.checks)

    # First row is Our Company
    assert landscape['orgs'][0]['is_us'] is True
    assert landscape['orgs'][0]['org_id'] == 'alpine-digital'
    assert landscape['orgs'][0]['cells']['R1']['raw_status'] == 'PASS'

    # Requirement advantage is analyzed
    assert 'advantages' in landscape
    assert 'R1' in landscape['advantages']
    assert landscape['advantages']['R1']['advantage'] in ['LOW DIFFERENTIATION', 'HIGH ADVANTAGE', 'MARKET BARRIER', 'NEUTRAL']


def test_competitor_candidate_generation():
    from src.opportunity.competitors import generate_competitor_candidates
    candidates = generate_competitor_candidates(
        scope='IT infrastructure and cloud migration operations',
        buyer='Demonstration Canton of Vaud',
    )
    assert len(candidates) >= 1
    # Helvetia IT is an incumbent for Demonstration Canton of Vaud
    cand_ids = [c['org_id'] for c in candidates]
    assert 'helvetia-it' in cand_ids
    incumbent = next(c for c in candidates if c['org_id'] == 'helvetia-it')
    assert incumbent['category'] == 'Incumbent supplier'
