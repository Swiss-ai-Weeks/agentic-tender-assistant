"""Tender Compiler: natural-language clauses in, executable rule candidates out.

The LLM (Nemotron, P1) may propose candidate rules; this module is the
deterministic gate that validates, compiles or refuses them. Ambiguous language
is never given invented deterministic meaning: it stays AMBIGUOUS.
"""
import re

from src.opportunity.models import Requirement, Source

VERSION = 'compiler/0.3'

FIELDS = {'references': 'references', 'insurance': 'insurance', 'certifications': 'certifications',
          'revenue': 'revenue', 'languages': 'languages'}
UNITS = {'references': 'projects', 'insurance': 'CHF', 'revenue': 'CHF', 'certifications': 'names', 'languages': 'languages'}
WORD_NUMBERS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
                'deux': 2, 'trois': 3, 'quatre': 4, 'cinq': 5, 'dix': 10,
                'eins': 1, 'ein': 1, 'zwei': 2, 'drei': 3, 'vier': 4, 'fünf': 5, 'sechs': 6, 'sieben': 7, 'acht': 8, 'neun': 9, 'zehn': 10}
LANGUAGES = ['French', 'German', 'English', 'Italian', 'Français', 'Allemand', 'Anglais', 'Italien',
             'Französisch', 'Deutsch', 'Englisch', 'Italienisch']
LANG_MAP = {name.casefold(): {'français': 'French', 'französisch': 'French', 'allemand': 'German', 'deutsch': 'German',
                              'anglais': 'English', 'englisch': 'English', 'italien': 'Italian', 'italienisch': 'Italian'}
            .get(name.casefold(), name) for name in LANGUAGES}
HEDGES = r"should|may|is encouraged|is welcome|ideally|desirable|devrait|souhaitable|bienvenue|\bsoll\b|\bkann\b|wünschenswert"
MANDATORY = r"\b(?:must|shall|is required|obligatoire|doit|muss|verpflichtet|erforderlich)\b"
NO_THRESHOLD = r"substantial|significant|appropriate|proven|several|extensive|sufficient|adäquat|ausreichend|erheblich|entsprechend|angemessen|zumutbar"
NUM = r"(?:\d{1,3}(?:[',]\d{3})+|\d+(?:[.,]\d+)?)"
WORD_ALT = '|'.join(sorted(WORD_NUMBERS, key=len, reverse=True))
LANG_ALT = '|'.join(sorted(LANGUAGES, key=len, reverse=True))


class CompiledRule:
    """Internal rule representation. Linked back to its clause by source."""

    def __init__(self, ident, field, operator, expected, unit, mandatory, status, reason,
                 raw_clause, source, window_years=None, label=None):
        self.id, self.field, self.operator, self.expected = ident, field, operator, expected
        self.unit, self.mandatory, self.status, self.reason = unit, mandatory, status, reason
        self.raw_clause, self.source, self.window_years, self.label = raw_clause, source, window_years, label

    def to_requirement(self) -> Requirement:
        return Requirement(id=self.id, label=self.label or self.raw_clause[:80], field=self.field,
                           operator=self.operator, expected=self.expected, unit=self.unit,
                           mandatory=self.mandatory, source=self.source, raw_clause=self.raw_clause,
                           compile_status=self.status, compile_reason=self.reason, window_years=self.window_years)


def refuse(ident, clause, source, status, reason, mandatory=True) -> CompiledRule:
    field = 'review'
    return CompiledRule(ident, field, 'review', clause[:60], '', mandatory, status, reason, clause, source,
                        label=f'{clause[:60]}{"…" if len(clause) > 60 else ""}')


def threshold_number(clause: str, keyword: str) -> float | None:
    match = re.search(keyword + r"[^.]{0,80}?(" + NUM + r")\s*(millions?|mio\b|m\b)?", clause, re.IGNORECASE)
    if not match:
        return None
    value = float(re.sub(r"[',\s]", '', match.group(1)).replace(',', '.'))
    if match.group(2):
        value *= 1_000_000
    return value


def language_name(raw: str) -> str | None:
    """Resolve an inflected language mention ('deutscher', 'französische') to a
    canonical language name, or None when it is not a recognised language."""
    key = raw.casefold()
    for candidate in [key] + [key[: -len(suffix)] for suffix in ['er', 'es', 'en', 'e'] if key.endswith(suffix)]:
        if candidate in LANG_MAP:
            name = LANG_MAP[candidate]
            if name in ['French', 'German', 'English', 'Italian']:
                return name
    return None


def compile_clause(clause: str, source: Source, ident: str, candidate: dict | None = None) -> CompiledRule:
    """Compile one raw clause. `candidate` is an optional LLM-proposed rule dict;
    it is accepted only after deterministic validation against the clause text."""
    text = ' '.join(clause.split())
    mandatory = re.search(MANDATORY, text, re.IGNORECASE) is not None
    hedged = re.search(HEDGES, text, re.IGNORECASE) is not None and not mandatory
    if hedged:
        return refuse(ident, text, source, 'AMBIGUOUS',
                      'Hedged obligation language ("should/may"): not an enforceable mandatory gate; needs human interpretation.',
                      mandatory=False)
    if re.search(NO_THRESHOLD, text, re.IGNORECASE) and not re.search(rf"{NUM}|\b(?:{WORD_ALT})\b", text, re.IGNORECASE):
        return refuse(ident, text, source, 'AMBIGUOUS',
                      'Requirement without an explicit threshold (e.g. "substantial", "sufficient"): cannot safely compile.',
                      mandatory=mandatory)

    # References: "at least three comparable projects completed within the previous five years"
    if re.search(r"(?:comparable|similar|relevant)\s+(?:projects?|references?|contracts?)|(?:projets?|références?)\s+comparables|(?:Referenzen|Projekte|Referenzprojekte)\s+mit\s+vergleichbar|vergleichbar\w*\s+(?:Projekte|Referenzen|Leistungen|Referenzprojekte)|Erfahrung\s+mit", text, re.IGNORECASE):
        match = re.search(r"(?:at least|no fewer than|minimum(?: of)?|au moins|mindestens)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|deux|trois|quatre|cinq|dix|eins|ein|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn)\s+"
                          r"(?:(?:other\s+)?(?:comparabl\w*|similar|relevant|vergleichbar\w*)?\s*(?:other\s+)?)?(?:projects?|references?|contracts?|projets?|références?|marchés?|Referenzen|Referenzprojekte|Projekte)", text, re.IGNORECASE)
        if match:
            expected = WORD_NUMBERS.get(match.group(1).casefold()) or int(match.group(1))
            window = re.search(r"(?:within|during|in)\s+the\s+(?:previous|past|last)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|cinq|dix|eins|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn)\s+years?", text, re.IGNORECASE) or \
                     re.search(r"(?:au cours des|pendant les|dans les)\s+(\d+|cinq|trois|quatre|dix|deux)\s+dernières\s+années", text, re.IGNORECASE) or \
                     re.search(r"(?:innerhalb|während|in)\s+der\s+letzten\s+(\d+|eins|ein|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn)\s+Jahre", text, re.IGNORECASE) or \
                     re.search(r"max(?:imal)?\.?\s+(\d+|eins|ein|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn)\s+Jahren?\s+zurück", text, re.IGNORECASE)
            window_years = WORD_NUMBERS.get(window.group(1).casefold()) or int(window.group(1)) if window else None
            status = 'VERIFIED' if re.search(r"comparabl|vergleichbar", text, re.IGNORECASE) and window_years else 'NEEDS_REVIEW'
            reason = '' if status == 'VERIFIED' else 'Recency window or comparability basis is not explicit.'
            return CompiledRule(ident, 'references', '>=', float(expected), 'projects', mandatory, status, reason,
                                text, source, window_years,
                                label=f'≥{expected} comparable references' + (f' in {window_years} years' if window_years else ''))
        bare = re.search(r"(\d+|eins|ein|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn)\s+(?:andere\s+)?(?:vergleichbare\s+)?(?:Referenzen|Referenzprojekte|Projekte|projects?|references?)", text, re.IGNORECASE)
        if bare:
            return refuse(ident, text, source, 'NEEDS_REVIEW',
                          'A reference count is stated without an explicit "at least/mindestens" bound; the intended comparison operator must be confirmed.')
        return refuse(ident, text, source, 'NEEDS_REVIEW', 'Reference requirement without a countable threshold.')

    # Insurance: "professional liability insurance coverage of at least CHF 10,000,000"
    if re.search(r"(?:professional\s+)?liability\s+(?:insurance|coverage|indemnity)|assurance\s+responsabilité|haftpflicht(?:versicherung)?", text, re.IGNORECASE):
        value = threshold_number(text, r"(?:coverage|insurance|indemnity|couverture|assurance|montant|versicherung|deckung)")
        if value:
            operator = '>=' if re.search(r"at least|no less than|minimum|au moins|mindestens", text, re.IGNORECASE) else '='
            status = 'VERIFIED' if operator == '>=' else 'NEEDS_REVIEW'
            reason = '' if operator == '>=' else 'Comparison operator is implicit; confirm the intended bound.'
            return CompiledRule(ident, 'insurance', '>=', value, 'CHF', mandatory,
                                status, reason, text, source, label=f'Liability insurance ≥ CHF {value:,.0f}')
        return refuse(ident, text, source, 'NEEDS_REVIEW', 'Insurance requirement without a stated coverage amount.')

    # Certification: "must hold a valid ISO 27001 information security certification"
    match = re.search(r"\b(ISO|IEC)[\s/-]?(\d{4,5})\b", text)
    if match:
        expected = f'{match.group(1).upper()} {match.group(2)}'
        return CompiledRule(ident, 'certifications', 'contains', expected, 'names', mandatory, 'VERIFIED', '',
                            text, source, label=f'{expected} certification')
    if re.search(r"certification|certificate|zertifikat|partner-status", text, re.IGNORECASE):
        return refuse(ident, text, source, 'NEEDS_REVIEW', 'Certification named without a recognised standard identifier.')

    # Revenue / turnover: "annual turnover of at least CHF 5,000,000"
    if re.search(r"(?:annual\s+)?(?:turnover|revenue|chiffre d'affaires)|(?:jahres-)?umsatz", text, re.IGNORECASE):
        value = threshold_number(text, r"(?:turnover|revenue|chiffre d'affaires|umsatz)")
        if value:
            operator = '>=' if re.search(r"at least|no less than|exceeding|minimum|au moins|supérieur|mindestens", text, re.IGNORECASE) else '='
            status = 'VERIFIED' if operator == '>=' else 'NEEDS_REVIEW'
            return CompiledRule(ident, 'revenue', '>=', value, 'CHF', mandatory, status,
                                '' if status == 'VERIFIED' else 'Comparison operator is implicit.', text, source,
                                label=f'Annual turnover ≥ CHF {value:,.0f}')
        return refuse(ident, text, source, 'NEEDS_REVIEW', 'Financial requirement without a stated amount.')

    # Language: "Services must be delivered in French." / "French-speaking project manager" / "in deutscher Sprache"
    match = re.search(rf"(?:delivered|provided|rendered|exécutés?)\s+in\s+({LANG_ALT})\b", text, re.IGNORECASE) or \
            re.search(rf"\b({LANG_ALT})-speaking", text, re.IGNORECASE) or \
            re.search(rf"in\s+((?:{LANG_ALT})[a-z]*)\s+Sprache", text, re.IGNORECASE)
    if match:
        expected = language_name(match.group(1))
        if expected:
            return CompiledRule(ident, 'languages', 'contains', expected, 'languages', mandatory, 'VERIFIED', '',
                                text, source, label=f'{expected} service delivery')

    if candidate is not None:
        return validate_candidate(text, source, ident, candidate, mandatory)
    return refuse(ident, text, source, 'UNSUPPORTED',
                  'No compilable constraint structure recognised in this clause; human interpretation required.')


def validate_candidate(clause: str, source: Source, ident: str, candidate: dict, mandatory: bool = True) -> CompiledRule:
    """Deterministic acceptance gate for an LLM-proposed rule. A candidate is
    accepted only when its type, threshold and units are literally supported by
    the clause text; otherwise the clause is escalated, never guessed."""
    field, operator = candidate.get('field'), candidate.get('operator')
    expected = candidate.get('expected')
    if field not in FIELDS or operator not in ['>=', 'contains']:
        return refuse(ident, clause, source, 'NEEDS_REVIEW', 'Candidate rule used an unsupported field or operator.')
    if field == 'certifications':
        # Build the pattern outside the f-string so this stays valid on the
        # repository's supported Python 3.11 runtime as well as 3.12.
        pattern = re.escape(str(expected)).replace(' ', r'[\s/-]?')
        if isinstance(expected, str) and re.search(rf"\b{pattern}\b", clause, re.IGNORECASE):
            return CompiledRule(ident, field, 'contains', expected, 'names', mandatory, 'VERIFIED', '', clause, source,
                                label=f'{expected} certification')
    else:
        if isinstance(expected, (int, float)) and str(expected) in clause.replace("'", '').replace(',', ''):
            return CompiledRule(ident, field, operator, expected, UNITS[field], mandatory, 'VERIFIED', '', clause, source,
                                label=f'{field} {operator} {expected:,.0f}')
    return refuse(ident, clause, source, 'NEEDS_REVIEW', 'Candidate rule could not be anchored to the clause text.')
