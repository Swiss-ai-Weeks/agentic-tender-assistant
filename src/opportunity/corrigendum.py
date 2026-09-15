"""Corrigendum recompilation: when a tender changes, recompile and show what moved.

Each clause is compiled for both versions; changed, added and removed rules are
reported individually, and re-qualification shows the decision delta. Previous
versions are never overwritten (see sources.store_version).
"""
from src.opportunity.compiler import compile_clause

PAYLOAD = ('field', 'operator', 'expected', 'unit', 'window_years', 'mandatory')


def _compile_all(clauses: dict[str, str], source) -> dict:
    return {ident: compile_clause(text, source, ident) for ident, text in clauses.items()}


def describe(rule) -> str:
    if rule.status in ['AMBIGUOUS', 'NEEDS_REVIEW', 'UNSUPPORTED']:
        return f'{rule.status}: {rule.reason}'
    target = f'{rule.expected:,.0f} {rule.unit}'.strip() if isinstance(rule.expected, (int, float)) else str(rule.expected)
    window = f' within {rule.window_years}y' if rule.window_years else ''
    return f'{rule.field} {rule.operator} {target}{window}'


def recompile_diff(old_clauses: dict[str, str], new_clauses: dict[str, str], source) -> dict:
    old = _compile_all(old_clauses, source)
    new = _compile_all(new_clauses, source)
    changes = []
    for ident in sorted(set(old) | set(new)):
        before, after = old.get(ident), new.get(ident)
        if before is None:
            changes.append({'id': ident, 'kind': 'ADDED', 'new': describe(after), 'clause': after.raw_clause})
        elif after is None:
            changes.append({'id': ident, 'kind': 'REMOVED', 'old': describe(before), 'clause': before.raw_clause})
        elif tuple(getattr(before, k) for k in PAYLOAD) != tuple(getattr(after, k) for k in PAYLOAD):
            changes.append({'id': ident, 'kind': 'CHANGED',
                            'old': describe(before), 'new': describe(after),
                            'clause': after.raw_clause, 'old_clause': before.raw_clause})
    return {'changed': bool(changes), 'changes': changes,
            'note': 'Only impacted requirements are recompiled; the previous tender version remains stored and auditable.'}


def demo_pair() -> tuple[dict, dict]:
    """Controlled corrigendum pair: a reference threshold tightens and a new
    insurance requirement is added — the demo used in the jury walkthrough."""
    old = {'R2': 'The bidder must demonstrate at least three comparable projects completed within the previous five years.',
           'R3': 'Services must be delivered in French.'}
    new = {'R2': 'The bidder must demonstrate at least five comparable projects completed within the previous five years.',
           'R3': 'Services must be delivered in French.',
           'R5': 'The bidder must provide professional liability insurance coverage of at least CHF 10,000,000.'}
    return old, new
