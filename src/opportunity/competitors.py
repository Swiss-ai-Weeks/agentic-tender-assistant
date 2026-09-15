"""Competitive qualification landscape.

The exact compiled requirement set of a tender is evaluated for competitor
organizations using public evidence only. Three states exist:
PUBLICLY SUPPORTED (public record satisfies the rule), PUBLIC NON-MATCH (public
record contradicts the rule) and UNKNOWN. Absence of public evidence is never a
NON-MATCH; UNKNOWN is mandatory when evidence is insufficient.
"""
from datetime import date

from src.opportunity.facts import competitor_data, resolve_org
from src.opportunity.models import CompetitorStatus

SOURCE_TYPE = 'public record'


def _award_comparable(award: dict, scope: str) -> bool:
    """Deterministic comparability proxy: keyword overlap between the award
    description and the tender scope. Nemotron (P1) may refine this judgement;
    the counted evidence stays public and auditable."""
    text = (award.get('description', '') + ' ' + award.get('title', '')).casefold()
    words = [w for w in scope.casefold().replace(',', ' ').split() if len(w) > 3]
    return any(w in text for w in words)


def _reference_state(org_id: str, expected: float, window_years: int | None, deadline: str | None,
                     awards: list[dict], scope: str) -> tuple[CompetitorStatus, str, list[dict]]:
    cut = None
    if window_years and deadline:
        cut = (date.fromisoformat(deadline).replace(year=date.fromisoformat(deadline).year - window_years)).isoformat()
    comparable = []
    for award in awards:
        resolved = resolve_org(award['org'], competitor_data()['orgs'])
        if not resolved or resolved['id'] != org_id:
            continue
        if cut and award['date'] < cut:
            continue
        if _award_comparable(award, scope):
            comparable.append(award)
    evidence = [{'document': a['source']['document'], 'quote': a['source']['quote'], 'url': '/api/sources/competitors/' + a['source']['document'],
                 'trust': 'VERIFIED_PUBLIC'} for a in comparable]
    if len(comparable) >= expected:
        return 'PUBLICLY SUPPORTED', f'{len(comparable)} comparable public awards on record (threshold {expected:.0f}).', evidence
    return 'UNKNOWN', (f'{len(comparable)} comparable public awards found (threshold {expected:.0f}); '
                       'public registers are not exhaustive, so absence of more awards proves nothing.'), evidence


def _registry_state(org_id: str, requirement_field: str, expected) -> tuple[CompetitorStatus, str, list[dict]]:
    data = competitor_data()
    matching = []
    for fact in data.get('registry_facts', []):
        resolved = resolve_org(fact['org'], data['orgs'])
        if resolved and resolved['id'] == org_id and fact['predicate'] == requirement_field:
            matching.append(fact)
    evidence = [{'document': f['source']['document'], 'quote': f['source']['quote'],
                 'url': '/api/sources/competitors/' + f['source']['document'], 'trust': f.get('trust', 'VERIFIED_PUBLIC')} for f in matching]
    for fact in matching:
        if fact.get('contradicts'):
            return 'PUBLIC NON-MATCH', fact['note'], evidence
        if requirement_field == 'certifications' and isinstance(fact.get('value'), list):
            if expected in [str(v) for v in fact['value']]:
                return 'PUBLICLY SUPPORTED', f'Public registry lists {expected} (valid until {fact.get("valid_until", "stated validity")}).', evidence
    return 'UNKNOWN', 'No public registry record located for this requirement; absence of evidence is not a negative finding.', evidence


def competitor_landscape(requirements: list, scope: str, deadline: str | None) -> dict:
    """Landscape rows for one tender's mandatory requirements across known competitors."""
    data = competitor_data()
    rows = []
    for org in data['orgs']:
        cells = {}
        for req in requirements:
            if not req.mandatory or req.compile_status != 'VERIFIED':
                continue
            if req.field == 'references':
                status, note, evidence = _reference_state(org['id'], float(req.expected), req.window_years, deadline, data['awards'], scope)
            else:
                status, note, evidence = _registry_state(org['id'], req.field, str(req.expected))
            cells[req.id] = {'requirement': req.label, 'field': req.field, 'status': status, 'note': note, 'evidence': evidence}
        rows.append({'org': org['name'], 'org_id': org['id'], 'registry_id': org.get('registry_id'), 'cells': cells})
    return {'requirements': [{'id': r.id, 'label': r.label, 'field': r.field} for r in requirements
                             if r.mandatory and r.compile_status == 'VERIFIED'],
            'orgs': rows,
            'semantics': {'PUBLICLY SUPPORTED': 'A public record satisfies the compiled rule.',
                          'PUBLIC NON-MATCH': 'A public record contradicts the compiled rule.',
                          'UNKNOWN': 'Insufficient public evidence. Never interpreted as inability.'}}
