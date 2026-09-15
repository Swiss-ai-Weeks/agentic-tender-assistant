"""Organization facts are separate from the evidence that supports them.

Evidence files are immutable records; facts are typed statements derived from
them, carrying trust class, validity window and provenance. Inferred statements
never satisfy a mandatory requirement for our own company.
"""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from src.opportunity.models import Evidence, Source

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / 'data' / 'demo'
COMPETITORS = DEMO / 'competitors'


def file_source(path: Path, quote_text: str, line: int | None = None, url: str | None = None,
                trust: str = 'VERIFIED_INTERNAL') -> Source:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    source_id = str(path.relative_to(ROOT / 'data'))
    return Source(id=source_id, document=path.name, quote=quote_text, line=line,
                  url=url or '/api/sources/' + source_id.removeprefix('demo/'), trust=trust, sha256=digest,
                  retrieved_at=datetime.now(UTC).date().isoformat())


def read_evidence(name: str) -> list[Evidence]:
    path = DEMO / 'evidence' / name
    items = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        parts = [x.strip() for x in line.split('|')]
        if len(parts) not in (4, 5):
            continue
        field, value, unit, valid_until = parts[:4]
        observed_at = parts[4] if len(parts) == 5 else None
        parsed = float(value.replace(',', '')) if value.replace(',', '').replace('.', '', 1).isdigit() else value.split(',')
        items.append(Evidence(field=field, value=parsed, unit=unit, valid_until=valid_until,
                              source=file_source(path, line, n), trust='VERIFIED_INTERNAL', observed_at=observed_at))
    return items


def company_facts(files: list[str]) -> list[Evidence]:
    """Facts derived only from the configured verified internal evidence records."""
    return [fact for name in files for fact in read_evidence(name)]


def competitor_data() -> dict:
    return json.loads((COMPETITORS / 'registry.json').read_text())


def resolve_org(name: str, orgs: list[dict]) -> dict | None:
    """Entity resolution over canonical names, aliases and historical names."""
    needle = name.casefold().strip()
    for org in orgs:
        names = [org['name']] + org.get('aliases', [])
        if needle in [n.casefold().strip() for n in names]:
            return org
    return None
