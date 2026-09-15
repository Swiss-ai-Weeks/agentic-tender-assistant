"""Read-only SIMAP MCP discovery and conservative source-grounded notice extraction."""
from datetime import date
import html
import json
from pathlib import Path
import re
import subprocess

from src.opportunity.compiler import compile_clause
from src.opportunity.engine import ROOT, decide, company_profile
from src.opportunity.models import Check, Opportunity, ProofStep, Requirement, Source

CAPTURED = ROOT / 'data' / 'captured'


def mcp_call(tool, arguments):
    result = subprocess.run(['node', str(ROOT / 'integrations/simap/bridge.mjs'), tool,
                             json.dumps(arguments)], capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('SIMAP MCP transport unavailable. Choose stored notices or the synthetic walkthrough.')
    payload = json.loads(result.stdout)
    if payload.get('isError'):
        raise RuntimeError('SIMAP returned a tool error. No live results have been substituted.')
    return payload


def tool_text(payload):
    return '\n'.join(c.get('text', '') for c in payload.get('content', []) if c.get('type') == 'text')


def leads(payload):
    text = tool_text(payload)
    found = []
    for block in re.split(r'\n## ', text)[1:]:
        fields = dict(re.findall(r'- \*\*([^*]+):\*\* (.*)', block))
        if fields.get('Project ID') and fields.get('Publication ID'):
            found.append({'id': fields['Project ID'], 'publication': fields['Publication ID'],
                          'title': block.splitlines()[0], 'buyer': fields.get('Office', 'Not disclosed'),
                          'location': fields.get('Location', 'Not disclosed'),
                          'url': fields.get('simap Link'), 'text': block})
    return found


def relevant(lead):
    # Profile-configured multilingual discovery terms; no fixed tender ids.
    terms = company_profile()['search_terms'] + company_profile()['capabilities']
    return [term for term in terms if term.casefold() in lead['text'].casefold()]


def localized(value):
    if isinstance(value, dict):
        return next((value.get(k) for k in ['en', 'fr', 'de', 'it'] if value.get(k)), '')
    return value if isinstance(value, str) else ''


def plain(value):
    return html.unescape(re.sub('<[^>]+>', ' ', localized(value))).strip()


def raw_response(payload):
    text = tool_text(payload)
    match = re.search(r'```json\n(.*?)\n```', text, re.S)
    if not match:
        raise RuntimeError('SIMAP did not return a full notice; investigation requires manual review.')
    return json.loads(match.group(1))


def notice_opportunity(lead, payload, source_id, mode='live'):
    raw = raw_response(payload)
    # JSON pointer citations retain the exact published fields, including HTML.
    def source(pointer, value):
        return Source(id=source_id, document='SIMAP notice · ' + lead['title'],
                      quote=json.dumps(value, ensure_ascii=False), section=pointer,
                      url='/api/sources/' + source_id)
    base = raw.get('base') or {}
    info = raw.get('project-info') or {}
    address = info.get('procOfficeAddress') or {}
    procurement = raw.get('procurement') or {}
    dates = raw.get('dates') or {}
    title = localized(base.get('title')) or lead['title']
    buyer = localized(address.get('name')) or lead['buyer']
    scope = plain(procurement.get('orderDescription'))
    deadline = dates.get('offerDeadline')
    facts = {'title': source('/base/title', base.get('title')),
             'buyer': source('/project-info/procOfficeAddress/name', address.get('name')),
             'scope': source('/procurement/orderDescription', procurement.get('orderDescription'))}
    if deadline:
        facts['deadline'] = source('/dates/offerDeadline', deadline)
    checks = []
    family_terms = [('certifications', ['zertif', 'partner-status', 'certificat']),
                    ('references', ['referenz', 'erfahrung', 'référence']),
                    ('capacity', ['kapazität', 'capacité']), ('legal', ['rechtspers', 'juristi']),
                    ('languages', ['sprache', 'langue']), ('insurance', ['versicherung', 'assurance']),
                    ('team', ['personal', 'personnel', 'mitarbeitend'])]
    # Preserve lot scope rather than merging different lots into one invented rule.
    groups = [('/criteria', raw.get('criteria') or {})]
    groups += [(f'/lots/{i}', lot) for i, lot in enumerate(raw.get('lots') or [])]
    for path, group in groups:
        for i, criterion in enumerate(group.get('qualificationCriteria') or []):
            text = plain(criterion.get('title')) + ': ' + plain(criterion.get('description'))
            family = next((f for f, words in family_terms if any(w in text.casefold() for w in words)), 'technical')
            label = (f"Lot {group['lotNumber']} · " if 'lotNumber' in group else '') + text
            ident = criterion.get('id') or f'{path}-{i}'
            criterion_source = source(f'{path}/qualificationCriteria/{i}', criterion)
            rule = compile_clause(text, criterion_source, ident)
            if rule.status == 'VERIFIED' and rule.mandatory:
                # Executable rule from a real notice: still UNKNOWN until verified
                # bidder evidence exists — fictional demo evidence never applies here.
                req = rule.to_requirement()
                req.label = label[:120]
                checks.append(Check(requirement=req, status='UNKNOWN',
                                    reason=f'Compiled executable rule ({rule.label}); awaiting verified bidder evidence for this real notice.',
                                    action='Provide verified company evidence for this compiled requirement.',
                                    proof=[ProofStep(stage='CLAUSE', text=text, ref=criterion_source.url),
                                           ProofStep(stage='RULE', text=f'{req.id}: {rule.label} · compiled VERIFIED'),
                                           ProofStep(stage='FACT', text='No verified bidder fact configured for real notices.'),
                                           ProofStep(stage='VERDICT', text='UNKNOWN — compiled rule awaits verified evidence.')]))
            else:
                # Published criteria stay conservative: review-gated with the compiler's honest status.
                req = Requirement(id=ident, label=label, field=family, operator='review',
                                  expected='Verified supporting evidence', raw_clause=text,
                                  compile_status=rule.status,
                                  compile_reason=rule.reason or 'Published criterion extracted verbatim; interpretation requires the full specification.',
                                  source=criterion_source)
                checks.append(Check(requirement=req, status='UNKNOWN',
                                    reason='Published criterion not compiled into an executable rule; interpretation and evidence require validation.',
                                    action='Review the cited criterion and provide its requested evidence: ' + (plain(criterion.get('verification')) or 'confirm with the tender documents.'),
                                    proof=[ProofStep(stage='CLAUSE', text=text, ref=criterion_source.url),
                                           ProofStep(stage='RULE', text=f'{req.id}: not executable · {rule.status} — {rule.reason or "no compilable structure"}'),
                                           ProofStep(stage='VERDICT', text='UNKNOWN — human interpretation required.')]))
    url = lead.get('url') or ''
    op = Opportunity(id=lead['id'], title=title, buyer=buyer,
                     location=plain(address.get('city')) or lead['location'],
                     deadline=deadline[:10] if deadline else None, summary=scope or 'Read the published notice for the full scope.',
                     mode=mode, source=facts['title'], facts=facts, checks=checks,
                     fit_matches=relevant(lead), why=[f'Company search term matched: {x}.' for x in relevant(lead)],
                     risks=['Notice-level extraction only. External specifications and lot-specific award criteria require review.',
                            'Company profile is fictional demonstration data; verify real bidder evidence before making a business decision.'])
    if url.startswith('https://www.simap.ch/'):
        op.next_steps.append('Open the official notice: ' + url)
    # Values are deliberately read only from explicit recognized amount/currency pairs.
    # Unknown keys, award amounts and document fees must not be mistaken for contract value.
    for key in ['estimatedContractValue', 'maximumContractValue', 'contractValue']:
        value = procurement.get(key)
        if isinstance(value, dict) and isinstance(value.get('amount'), (int, float)) and value.get('currency'):
            op.contract_value = value['amount']
            op.value_currency = value['currency']
            op.value_basis = key
            op.value_source = source('/procurement/' + key, value)
            break
    return decide(op, date.today())
