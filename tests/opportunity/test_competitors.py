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
        insurance = row['cells']['R1']
        assert insurance['status'] in ['UNKNOWN']  # no public insurance registry data exists
